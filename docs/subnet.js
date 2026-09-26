'use strict';
// Pure IPv4 arithmetic. No networking, device access, or host enumeration.
function parseIPv4(value) {
  if (typeof value !== 'string') throw new Error('IPv4 address must be text.');
  const parts = value.trim().split('.');
  if (parts.length !== 4 || parts.some(part => !/^(0|[1-9][0-9]{0,2})$/.test(part) || Number(part) > 255)) {
    throw new Error('Enter four IPv4 octets between 0 and 255, without leading zeros.');
  }
  return parts.reduce((address, part) => address * 256 + Number(part), 0);
}
function formatIPv4(value) {
  return [24, 16, 8, 0].map(shift => (value >>> shift) & 255).join('.');
}
function calculateSubnet(ipText, maskText) {
  const ip = parseIPv4(ipText);
  if (typeof maskText !== 'string') throw new Error('Mask must be text.');
  const text = maskText.trim();
  let prefix;
  if (/^\/?[0-9]{1,2}$/.test(text)) {
    prefix = Number(text.replace('/', ''));
    if (prefix > 32) throw new Error('Prefix must be between 0 and 32.');
  } else {
    const suppliedMask = parseIPv4(text);
    const inverse = (~suppliedMask) >>> 0;
    if ((inverse & (inverse + 1)) !== 0) throw new Error('Subnet mask must contain contiguous leading ones.');
    prefix = 32 - Math.log2(inverse + 1);
  }
  const size = 2 ** (32 - prefix);
  const mask = (0xFFFFFFFF - size + 1) >>> 0;
  const network = (ip & mask) >>> 0;
  const broadcast = network + size - 1;
  const small = prefix >= 31;
  return {ip: formatIPv4(ip), mask: formatIPv4(mask), network: formatIPv4(network),
    broadcast: formatIPv4(broadcast), first_host: formatIPv4(small ? network : network + 1),
    last_host: formatIPv4(small ? broadcast : broadcast - 1), num_hosts: small ? size : size - 2,
    prefix, source: 'JavaScript (browser)'};
}
if (typeof module !== 'undefined') module.exports = {calculateSubnet};
