'use strict';
const form = document.getElementById('calculator');
function render() {
  const error = document.getElementById('error');
  const results = document.getElementById('results');
  error.hidden = true;
  try {
    const data = calculateSubnet(form.elements.ip.value, form.elements.mask.value);
    const list = document.getElementById('values');
    list.replaceChildren();
    const fields = [['network', 'Network address'], ['mask', 'Subnet mask'], ['broadcast', 'Last address / broadcast'], ['first_host', 'First usable address'], ['last_host', 'Last usable address'], ['num_hosts', 'Usable addresses']];
    fields.forEach(([key, label]) => {
      const box = document.createElement('div');
      const term = document.createElement('dt');
      const value = document.createElement('dd');
      term.textContent = label;
      value.textContent = key === 'num_hosts' ? data[key].toLocaleString('en-US') : data[key];
      box.append(term, value); list.append(box);
    });
    document.getElementById('note').textContent = data.prefix === 31 ? '/31 uses both addresses for point-to-point links (RFC 3021); no directed broadcast.' : data.prefix === 32 ? '/32 identifies one host. All address fields refer to that same address; no directed broadcast.' : `/${data.prefix} reserves the first address for the network and the last for broadcast. Counts reflect subnet arithmetic, not public routability.`;
    results.hidden = false;
  } catch (exception) {
    results.hidden = true;
    error.textContent = exception.message;
    error.hidden = false;
  }
}
form.addEventListener('submit', event => { event.preventDefault(); render(); });
document.querySelectorAll('[data-ip]').forEach(button => button.addEventListener('click', () => {
  form.elements.ip.value = button.dataset.ip;
  form.elements.mask.value = button.dataset.mask;
  render();
}));
