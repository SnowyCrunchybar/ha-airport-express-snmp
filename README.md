# AirPort Express SNMP for Home Assistant

[![Work in Progress](https://img.shields.io/badge/status-work%20in%20progress-yellow.svg)](https://github.com/SnowyCrunchybar/ha-airport-express-snmp)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=SnowyCrunchybar&repository=ha-airport-express-snmp&category=integration)

> **Language / Kieli:** [English](#english) | [Suomi](#suomi)

---

<a name="english"></a>
## 🇬🇧 English

> **🚧 Work in Progress:** This integration is actively being developed and tested on an Apple AirPort Express 2nd Generation (A1392, firmware 7.8.1). Features, entity names, and options may still evolve.

A lightweight, local-polling Home Assistant custom integration for monitoring an **Apple AirPort Express (A1392 / 2nd Gen)** base station using pure-Python async **SNMPv2c** (zero external Python dependencies).

### Features

- **Two-Step Config Flow & Options Flow:**
  - **Step 1:** Enter IP address, SNMP Community string, and polling interval (default `15` s).
  - **Step 2 (also editable later via Configure):**
    - **Monitored Interfaces:** Choose between *Core interfaces only (`WAN eth0`, `Wi-Fi 2.4 GHz wlan0`, `Wi-Fi 5 GHz wlan1`)* or *All interfaces (`WAN`, `LAN`, `2.4 GHz`, `5 GHz`, `Bridge`)*.
    - **Base Station System Info:** Uptime (`s`), connected Wi-Fi client count (`clients` + full client list with MAC, IP, RSSI, noise, SNR, link rate, and connection duration in entity attributes), and active DHCP lease count.
    - **Interface Data Rates (`Mbit/s`):** Real-time download and upload throughput with 32-bit counter rollover protection.
    - **Interface Traffic Totals & Status:** Cumulative byte counters (`B`), interface operational status, and diagnostic packet error counters (disabled by default).
    - **Client Presence Tracking (`device_tracker`):** Automatically links connected Wi-Fi clients via MAC address (`CONNECTION_NETWORK_MAC`) to existing Home Assistant devices (*Connected devices*).
    - **Client Technical Wi-Fi Diagnostics:** Per-client **RSSI (`dBm`)**, **SNR (`dB`)**, and **Link Rate (`Mbit/s`)** diagnostic sensors attached directly to each client's device page, plus a per-client **IP Address** diagnostic sensor (created disabled by default so you can enable it only for specific devices like local-control iPads).

### Installation

#### Option 1: HACS (Recommended)
1. Click the **Open in HACS** badge at the top of this README, or open **HACS > Integrations > ⋮ > Custom repositories**, add `https://github.com/SnowyCrunchybar/ha-airport-express-snmp` with category **Integration**, and install **AirPort Express SNMP**.
2. Restart Home Assistant.
3. Go to **Settings > Devices & Services > Add Integration**, search for **AirPort Express SNMP**, and follow the setup wizard.

#### Option 2: Manual
1. Copy `custom_components/airport_express_snmp` into your Home Assistant `/config/custom_components/` directory.
2. Restart Home Assistant and add **AirPort Express SNMP** via **Settings > Devices & Services**.

### AirPort Express Setup
1. Open **AirPort Utility 5.6.1** (or compatible configuration tool).
2. Go to **Advanced > Logging & Statistics**.
3. Enable **Allow SNMP** (keep *Allow SNMP over WAN* disabled unless needed) and set your desired **SNMP Community String**.

---

<a name="suomi"></a>
## 🇫🇮 Suomi

> **🚧 Work in Progress (Kehitysversio):** Tämä integraatio on aktiivisessa kehityksessä ja testauksessa Apple AirPort Express (2. sukupolvi, A1392, firmware 7.8.1) -tukiasemalla. Ominaisuudet ja entiteettien nimet voivat vielä täydentyä.

Kevyt, täysin paikallinen Home Assistant -integraatio **Apple AirPort Express (A1392 / 2. sukupolvi)** -tukiaseman seurantaan puhtaalla Pythonin asynkronisella **SNMPv2c**-toteutuksella (ei ulkoisia kirjastoriippuvuuksia).

### Ominaisuudet

- **Kaksivaiheinen käyttöönotto ja muokattavat asetukset (Config Flow & Options Flow):**
  - **Vaihe 1:** Syötä tukiaseman IP-osoite, SNMP Community -tunnus ja päivitysväli sekunteina (oletus `15` s).
  - **Vaihe 2 (muokattavissa myös jälkikäteen *Määritä*-painikkeesta):**
    - **Seurattavat verkkoliitännät:** Valitse *Vain tärkeimmät (`WAN eth0`, `Wi-Fi 2.4 GHz wlan0`, `Wi-Fi 5 GHz wlan1`)* tai *Kaikki liitännät (`WAN`, `LAN`, `2.4 GHz`, `5 GHz`, `Silta`)*.
    - **Tukiaseman yleiset tiedot:** Käyttöaika (`s`), yhdistettyjen Wi-Fi-asiakkaiden lukumäärä (`kpl` + täysi asiakaslista MAC-, IP-, RSSI-, kohina-, SNR-, linkkinopeus- ja yhteyden kestotietoineen attribuuteissa) sekä aktiiviset DHCP-vuokrat (`kpl`).
    - **Liitäntöjen siirtonopeudet (`Mbit/s`):** Reaaliaikainen lataus- ja lähetysnopeus 32-bittisen laskurin ylivuotosuojauksella.
    - **Liitäntöjen kokonaisliikenne ja tila:** Kumulatiiviset tavulaskurit (`B`), liitännän tila (`Yhdistetty` / `Katkaistu`) sekä diagnostiikan virhepakettilaskurit (oletuksena pois päältä).
    - **Laitteiden läsnäoloseuranta (`device_tracker`):** Linkittää yhdistetyt Wi-Fi-laitteet automaattisesti MAC-osoitteella (`CONNECTION_NETWORK_MAC`) olemassa oleviin Home Assistant -laitteisiin (*Yhdistetyt laitteet* -osioon).
    - **Laitteiden tekniset Wi-Fi-tiedot:** Laitekohtaiset **Signaali RSSI (`dBm`)**, **SNR (`dB`)** ja **Linkkinopeus (`Mbit/s`)** -diagnostiikkasensorit suoraan kunkin laitteen tietosivun alle, sekä laitekohtainen **IP-osoite**-diagnostiikkasensori (luodaan oletuksena pois päältä, jotta voit aktivoida sen vain haluamillesi laitteille, kuten paikallisohjauksessa olevalle iPadille).

### Asennus

#### Vaihtoehto 1: HACS (Suositeltu)
1. Klikkaa tämän sivun yläreunassa olevaa **Open in HACS** -painiketta tai avaa **HACS > Integraatiot > ⋮ > Mukautetut tietovarastot**, lisää `https://github.com/SnowyCrunchybar/ha-airport-express-snmp` kategorialla **Integration** ja lataa **AirPort Express SNMP**.
2. Käynnistä Home Assistant uudelleen.
3. Avaa **Asetukset > Laitteet ja palvelut > Lisää integraatio**, hae **AirPort Express SNMP** ja seuraa ohjattua käyttöönottoa.

#### Vaihtoehto 2: Manuaalinen asennus
1. Kopioi kansio `custom_components/airport_express_snmp` Home Assistantin hakemistoon `/config/custom_components/`.
2. Käynnistä Home Assistant uudelleen ja lisää **AirPort Express SNMP** kohdasta **Asetukset > Laitteet ja palvelut**.

### AirPort Expressin asetukset
1. Avaa **AirPort-työkalu 5.6.1** (tai yhteensopiva hallintatyökalu).
2. Siirry välilehdelle **Lisäasetukset > Lokit ja tilastot**.
3. Laita rasti ruutuun **Salli SNMP** (pidä *Salli SNMP WAN-portista* pois päältä, ellei sille ole erityistä tarvetta) ja aseta haluamasi **SNMP-alueen tunnus**.
