# Setting it all up

Everything arriving Saturday, in the order that wastes the least of your day.

The ordering is not arbitrary. The Pi has long unattended waits in it, so it goes first
and cooks while you do the fun part. WLED is second because it works in about twenty
minutes and gives you something to look at, which matters when the rest of this is
typing. The devices you already own go last, because each one is a credentials errand
rather than a wiring job.

| | | roughly |
|---|---|---|
| 1 | Flash the Pi and walk away | 10 min hands-on, 20 min waiting |
| 2 | LED strip and WLED | 45 min |
| 3 | Presence sensor | 30 min |
| 4 | Pi software and the certificate | 45 min |
| 5 | Pairing the things you already own | 1 hr, mostly account faff |
| 6 | The gaming PC | 15 min |
| 7 | The iPad | 20 min |

You do not need a soldering iron for any of it.

---

## 0. What everything is for

| Thing | Job |
|---|---|
| Raspberry Pi Zero 2 WH | Holds the connections the iPad legally cannot make itself |
| ESP32 #1 | Runs WLED, drives the strip |
| ESP32 #2 | Runs ESPHome, reads the presence sensor |
| WS2812B strip, 5V, 300 LEDs | Bias light behind the TV |
| 5V 10A supply | Powers the strip. Not optional, see below |
| Barrel screw terminals | Joins the supply's plug to the strip's bare wires |
| Kasa plugs ×2 | Anything with a normal plug that should turn on and off |
| LD2412 | Sees you walk in, so scenes fire without you asking |
| microSD, Pi power supply, data cable | Consumables, see the note at the end |

---

## 1. The Pi, first, because it involves waiting

On the Mac, install **Raspberry Pi Imager**. Choose **Raspberry Pi OS Lite (64-bit)**.
Lite, not Desktop: this thing has no monitor and a desktop it never draws is a desktop
eating a quarter of its memory.

**Before you hit write, open the gear/settings pane.** This is the entire difference
between a Pi that appears on your network and a Pi you have to plug a monitor into.
Set:

- hostname `wall`
- **enable SSH**, password authentication
- username and a password you'll remember
- your wifi SSID and password, country US

> **The Zero 2 W is 2.4GHz only.** If your router broadcasts one merged SSID for both
> bands this usually still works, but if the Pi never appears, this is the reason
> before it is anything else. Splitting out a 2.4GHz SSID for it is the fix.

Write the card, put it in the Pi, power it from the **PWR** port, not the middle one.
Give it three minutes on first boot. Then from the Mac:

```
ssh yourname@wall.local
```

If `wall.local` doesn't resolve, look in your router's client list for its IP and use
that. Leave it running, come back to it at step 4.

---

## 2. The strip and WLED

The satisfying part. Do this at the desk, not up a ladder; you mount it after it works.

### Flash the ESP32

Plug ESP32 #1 into the Mac with a **data** cable, then in **Chrome** open
`install.wled.me` and press Install.

> It must be Chrome or Edge. Safari has no WebSerial and the button will simply not do
> anything, with no error, which reads exactly like a dead board.

If no port appears in the picker, it's the cable 90% of the time. If it's definitely a
data cable, the board may need a CP210x or CH340 driver depending on which USB chip it
has, and the chip is printed on the board next to the USB socket.

When it finishes it asks for your wifi. Give it the same network the iPad is on.

### Wire it

The strip has three wires at one end. On BTF strips:

| wire | is | goes to |
|---|---|---|
| red | +5V | supply + |
| **white** | **ground** | supply − **and** ESP32 GND |
| green | data | ESP32 **GPIO2** |

> **White is ground, not black.** This is the single most common way this goes wrong,
> and backwards will not light and will not obviously fail either. You will spend an
> hour blaming the ESP32.

Power, in order:

1. Supply's barrel plug → **screw terminal connector** (the Thsinde ones). The terminal
   has + and − marked. Strip about 7mm, twist the strands tight, screw down, tug-test.
2. Terminal + → strip red. Terminal − → strip white.
3. **ESP32 5V pin → terminal +. ESP32 GND → terminal −.**

Step 3 is not optional and it's the one that gets skipped. The data line is a voltage
*relative to ground*, so if the ESP32 and the strip don't share a ground the strip sees
noise and flickers randomly, or does nothing.

> **Do not power the strip from the ESP32's USB port.** 300 LEDs at full white pull
> about 18A. USB gives you half an amp. You'd brown out the board, and best case it just
> resets over and over.

### Configure it, including the bit that matters

Browse to the ESP32's IP. **Config → LED Preferences**:

- **Length: 300**
- LED type: WS281x
- **Max current: 5000 mA**, and leave "auto-calculate brightness limit" **on**

That current cap is the answer to your fire worry, and it's a real answer rather than a
reassuring one. WLED measures what the pattern would draw and dims it to stay under the
number you set. With 5000mA set against a 10A supply you have a 2× margin, and you
physically cannot ask the strip to pull more than the wiring is good for. It also means
full white just comes out dimmer instead of browning out.

Set a colour. If the first few LEDs work and the rest don't, that's voltage drop over
5m: fine at the brightness you'll actually use, and the fix if it ever bothers you is
running a second pair of wires to the far end of the strip from the same terminals.

Now mount it. Behind the TV, on the back of the panel or on the wall just inside its
outline, so you see the light and not the diodes.

---

## 3. The presence sensor

ESP32 #2 with the LD2412. Use **web.esphome.io** in Chrome, same as before.

Wiring is four wires: 5V, GND, and the sensor's TX and RX crossed over to two spare
GPIOs (sensor TX → ESP32 RX, sensor RX → ESP32 TX). **Read the silkscreen on your actual
board rather than trusting a pinout from anywhere, including me** — these modules ship
with several pin orders and the labels on the board are the only authority.

In the ESPHome config, the LD2412 is a UART presence sensor; declare the UART on those
two pins and the sensor on top of it.

**Where to put it.** Not on the door frame. mmWave has a wide cone and sees movement,
including a curtain and including you rolling over in bed, so a sensor pointed at the
bed will report presence all night. High on the wall, aimed across the entry path and
away from the bed, is what you want. It has an adjustable maximum distance; set it just
past the doorway so it triggers on arrival rather than on everything.

You wanted it to not be a giant sensor at the door, and this is why mmWave rather than a
PIR: it can sit high and out of the way and still see you, where a PIR needs a clear
short line of sight to work at all.

---

## 4. The Pi's software, and the certificate

Back in that ssh session.

```
sudo apt update && sudo apt install -y python3-pip python3-venv git
git clone https://github.com/viaate/InternetWall
cd InternetWall/bridge
python3 -m venv .venv && . .venv/bin/activate
pip install aiohttp pyatv samsungtvws soco tinytuya
```

This takes a while on an ARM Pi Zero. Let it.

```
cp config.example.json config.json
nano config.json
```

Fill in what you know now, leave the credentials blank; the next section fills them.

### The certificate, which is the fiddly part

The wall is served from GitHub Pages over `https`, and **a secure page may not call an
insecure one**. There is no flag, no exception, no setting. So the Pi has to serve
`https` too, and the iPad has to genuinely trust it, because `fetch()` gives you no way
to click past a warning the way a page would.

On the **Mac**:

```
brew install mkcert
mkcert -install
mkcert wall.local
```

Copy the two `.pem` files to the Pi's `bridge/` directory as `cert.pem` and `key.pem`.

Then get mkcert's root CA onto the iPad. `mkcert -CAROOT` prints the folder; AirDrop
`rootCA.pem` to the iPad, then:

- **Settings → Profile Downloaded → Install**
- and then, separately, **Settings → General → About → Certificate Trust Settings**, and
  switch it on there.

> That second step is its own screen and installing the profile does not do it. If you
> skip it the certificate is installed and still not trusted, which looks identical to
> not having installed it.

Start it:

```
python3 bridge.py --config config.json
```

Visit `https://wall.local:8443/health` from the iPad's Safari. You want JSON, no
warning. Once that works, run it as a service so it survives a reboot.

---

## 5. The things you already own

Each of these is an errand for one credential.

**Sonos** — nothing to do. SoCo finds it on the network. Genuinely zero setup.

**Apple TV** — on the Pi:

```
atvremote scan
atvremote --id <the id> --protocol companion pair
```

A PIN appears on the TV, you type it, it prints credentials. Paste those into
`config.json` under `appletv.credentials`.

**Samsung** — nothing in advance. The first command the bridge sends makes the TV show
an allow/deny box. Say allow. The token it returns is written back to `config.json`
automatically, so it never asks again. If you miss the prompt, the command just fails;
send another and it reappears.

**Dyson TP07** — needs the device's own wifi credentials, which are on a **sticker on
the machine itself** (lift it and look, and they're also on a pull-out label and in the
manual). That gets you local MQTT on port 1883, which means real control and real air
quality numbers without a cloud round trip.

**The Tuya ceiling light and fan** — be warned, this is the annoying one. `tinytuya`
needs a per-device *local key*, and Tuya only hands those out through a free developer
account:

```
python3 -m tinytuya wizard
```

It walks you through making an account at iot.tuya.com, linking your Smart Life app, and
pulling the keys. Budget half an hour and a certain amount of irritation at Tuya. It is
worth doing exactly once, because afterwards the light is controlled over your LAN and
never touches their servers again.

**Kasa plugs** — set them up in the Kasa app first, then they answer on the LAN.

---

## 6. The gaming PC

Wake-on-LAN, three settings, and it will not work if you miss any:

1. **BIOS**: enable Wake on LAN / Power on by PCI-E.
2. **Windows → Device Manager → your Ethernet adapter → Properties**:
   - *Power Management* tab: allow this device to wake the computer, **and** only allow
     a magic packet to wake it.
   - *Advanced* tab: Wake on Magic Packet → Enabled.
3. **Turn off Fast Startup.** Control Panel → Power Options → Choose what the power
   buttons do → Change settings currently unavailable → untick *Turn on fast startup*.

That third one is the reason most WoL setups mysteriously don't work. Fast Startup means
Windows doesn't really shut down, it hibernates, and the network card gets powered off
on the way out.

Get its MAC from `ipconfig /all` (the Ethernet adapter's Physical Address) into
`config.json`.

---

## 7. The iPad

1. Open the Pages URL in Safari → **Share → Add to Home Screen**. Open it from the icon,
   not from Safari, or you get Safari's chrome.
2. Long-press bare wall → **Save all 8 clips to this iPad**. ~86MB, a few minutes.
3. Long-press bare wall → paste `https://wall.local:8443` into **Bridge address** → Done.
   It tells you what it found.
4. **Settings → Display & Brightness → Auto-Lock → Never.**
5. **Turn auto-brightness off**, then calibrate the idle level by eye from your chair.
6. **Settings → Accessibility → Guided Access → on.** Triple-click the side button to
   lock it to the app.

---

## The consumables you still need

Not in the cart, and everything stops without them:

- **microSD card**, 32GB, A1-rated. Not the cheapest no-name one; SD failure is how Pi
  projects die six months later.
- **micro-USB power supply**, 5V 2.5A. The Zero 2 W is micro-USB, not USB-C. An
  undervolted Pi throttles and drops wifi, which reads as "the remote randomly stops
  working."
- **A micro-USB cable that carries data**, for flashing the ESP32s.
- **Dupont jumper wires**, if they weren't in the order.

---

## When something doesn't work

**The strip does nothing.** Ground first: is white going to the same place as the
ESP32's GND? Then data: GPIO2, and into the strip's *input* end, which is the one the
arrows point away from.

**The strip flickers or shows wrong colours.** Almost always a missing common ground.

**Only the first LEDs light.** Voltage drop. Turn the brightness down, or feed 5V and
ground to the far end as well.

**WLED never joins the wifi.** It falls back to its own access point called `WLED-AP`,
password `wled1234`. Join that from your phone and set the wifi from there.

**The room page's buttons do nothing.** Long-press bare wall and check the bridge line.
"No answer" means the Pi is off or the certificate isn't trusted; those are the only two
causes, and the certificate one is the *Certificate Trust Settings* screen in step 4.

**The Pi never appears.** 2.4GHz, per step 1.

**The PC won't wake.** Fast Startup.
