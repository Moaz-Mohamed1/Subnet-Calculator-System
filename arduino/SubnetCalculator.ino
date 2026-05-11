/*
 * IP Subnet Calculator - Arduino Uno + Ethernet Shield
 * =====================================================
 * Listens for IP/Mask from PC, computes:
 *   - Network ID
 *   - Broadcast Address
 *   - First Host / Last Host
 *   - Number of Hosts
 * Responds back over Serial (USB) AND Ethernet (TCP).
 */

#include <SPI.h>
#include <Ethernet.h>

// ── MAC address ───────────────────────────────────────────────────────────────
byte mac[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED };

EthernetServer server(8080);

// ─────────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  Serial.println(F("=== Subnet Calculator Arduino ==="));

  IPAddress ip(192, 168, 1, 177);
  IPAddress gateway(192, 168, 0, 1);
  IPAddress subnet(255, 255, 255, 0);

  Ethernet.begin(mac, ip, gateway, gateway, subnet);

  delay(1000);
  Serial.print(F("Static IP: "));
  Serial.println(Ethernet.localIP());
  Serial.println(F("Waiting for connections on port 8080..."));

  server.begin();
}

// ─────────────────────────────────────────────────────────────────────────────
void loop() {
  Ethernet.maintain();

  // ── Serial (USB) input ────────────────────────────────────────────────────
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      Serial.println(processRequest(line));
    }
  }

  // ── Ethernet TCP client ───────────────────────────────────────────────────
  EthernetClient newClient = server.available();
  if (newClient) {
    Serial.println(F("[TCP] Client connected"));
    String request = "";

    unsigned long timeout = millis() + 3000;
    while (newClient.connected() && millis() < timeout) {
      if (newClient.available()) {
        char c = newClient.read();
        if (c == '\n') break;
        request += c;
      }
    }

    request = cleanString(request);

    if (request.length() > 0) {
      String result = processRequest(request);
      newClient.println(result);
      Serial.print(F("[TCP] Req: ")); Serial.println(request);
      Serial.print(F("[TCP] Res: ")); Serial.println(result);
    }

    newClient.stop();
    Serial.println(F("[TCP] Client disconnected"));
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// cleanString - يشيل اي \r \n او spaces
// ─────────────────────────────────────────────────────────────────────────────
String cleanString(String s) {
  String out = "";
  for (int i = 0; i < (int)s.length(); i++) {
    char c = s[i];
    if (c > 32 && c < 127) out += c;
  }
  return out;
}

// ─────────────────────────────────────────────────────────────────────────────
// processRequest - input: "192.168.1.50/255.255.255.0" او "192.168.1.50/24"
//                 output: JSON
// ─────────────────────────────────────────────────────────────────────────────
String processRequest(String input) {
  input = cleanString(input);

  Serial.print(F("[DBG] input: ")); Serial.println(input);

  // الفاصل هو / مش ,
  int slashIdx = input.indexOf('/');
  if (slashIdx < 0) return "{\"error\":\"missing slash\"}";

  String ipStr   = input.substring(0, slashIdx);
  String maskStr = input.substring(slashIdx + 1);

  Serial.print(F("[DBG] ip="));   Serial.println(ipStr);
  Serial.print(F("[DBG] mask=")); Serial.println(maskStr);

  uint32_t ip   = parseIP(ipStr);
  uint32_t mask = parseIP(maskStr);

  if (ip == 0)   return "{\"error\":\"bad ip\"}";
  if (mask == 0) return "{\"error\":\"bad mask\"}";

  // ── Compute ───────────────────────────────────────────────────────────────
  uint32_t network   = ip & mask;
  uint32_t broadcast = network | (~mask);
  uint32_t firstHost = network + 1;
  uint32_t lastHost  = broadcast - 1;
  uint32_t numHosts  = (~mask) - 1;

  // ── JSON ──────────────────────────────────────────────────────────────────
  String json = "{";
  json += "\"ip\":\""         + ipStr                 + "\",";
  json += "\"mask\":\""       + maskStr               + "\",";
  json += "\"network\":\""    + uint32ToIP(network)   + "\",";
  json += "\"broadcast\":\""  + uint32ToIP(broadcast) + "\",";
  json += "\"first_host\":\"" + uint32ToIP(firstHost) + "\",";
  json += "\"last_host\":\""  + uint32ToIP(lastHost)  + "\",";
  json += "\"num_hosts\":"    + String(numHosts);
  json += "}";
  return json;
}

// ─────────────────────────────────────────────────────────────────────────────
// parseIP - "192.168.1.1" → uint32   او   "24" → CIDR mask
// ─────────────────────────────────────────────────────────────────────────────
uint32_t parseIP(String s) {
  s = cleanString(s);

  // CIDR (e.g. "24") - مفيش نقطة
  if (s.indexOf('.') < 0) {
    int prefix = s.toInt();
    if (prefix <= 0 || prefix > 32) return 0;
    return (uint32_t)(0xFFFFFFFF) << (32 - prefix);
  }

  // Dotted decimal - 4 octets
  uint32_t result = 0;
  int octet = 0;
  int count = 0;

  for (int i = 0; i <= (int)s.length(); i++) {
    char c = (i < (int)s.length()) ? s[i] : '.';
    if (c == '.') {
      if (octet < 0 || octet > 255) return 0;
      result = (result << 8) | (uint8_t)octet;
      octet = 0;
      count++;
    } else if (c >= '0' && c <= '9') {
      octet = octet * 10 + (c - '0');
    } else {
      return 0;
    }
  }

  if (count != 4) return 0;
  return result;
}

// ─────────────────────────────────────────────────────────────────────────────
String uint32ToIP(uint32_t ip) {
  return String((ip >> 24) & 0xFF) + "." +
         String((ip >> 16) & 0xFF) + "." +
         String((ip >>  8) & 0xFF) + "." +
         String( ip        & 0xFF);
}
