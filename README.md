# AirPort Express SNMP for Home Assistant

HACS-yhteensopiva Home Assistant -integraatio Apple AirPort Express (A1392 / gen 2) -tukiaseman reaaliaikaiseen seurantaan SNMP-protokollan avulla.

## Ominaisuudet

- **Järjestelmätiedot:** Käyttöaika (uptime), laiteohjelmistoversio (`7.8.1`), mallikoodi (`1771`).
- **Wi-Fi-asiakkaat:** Yhdistettyjen laitteiden kokonaismäärä sekä attribuutteina jokaisen laitteen MAC-osoite, IP-osoite, signaalinvoimakkuus (RSSI dBm), kohinataso (dBm), SNR (dB), linkkinopeus (Mbps) ja yhteyden kesto.
- **DHCP-vuokrat:** Aktiivisten DHCP-osoitteiden lukumäärä.
- **Verkkoliitännät (`eth0` WAN, `eth1` LAN, `wlan0` 2.4 GHz, `wlan1` 5 GHz, `bridge0` Silta):**
  - Reaaliaikainen lataus- ja lähetysnopeus (`Mbit/s`)
  - Kokonaisliikenne sisään ja ulos (`B`)
  - Liitännän tila (`Yhdistetty` / `Katkaistu`)
- **Device Tracker:** Valinnainen läsnäoloseuranta (`device_tracker`) kaikille AirPort Expressiin yhdistetyille Wi-Fi-laitteille.

## Käyttöönotto

1. Ota **Salli SNMP** käyttöön AirPort-työkalussa (**Lisäasetukset > Lokit ja tilastot**) ja aseta haluamasi SNMP-alueen tunnus.
2. Lisää tämä repositorio HACS:iin (**Custom repositories > Integration**) ja asenna **AirPort Express SNMP**.
3. Käynnistä Home Assistant uudelleen.
4. Avaa **Asetukset > Laitteet ja palvelut > Lisää integraatio**, hae **AirPort Express SNMP** ja syötä tukiaseman IP-osoite sekä SNMP Community.
