# Building APK for Jogo Online (pygame)

This project uses pygame with SDL2. The easiest way to build an APK is via Buildozer (which wraps python-for-android). Building is supported on Linux; on Windows, use WSL2 Ubuntu.

## Prereqs (WSL2 Ubuntu or Linux)

1. Install WSL2 (Windows):
   - Enable "Windows Subsystem for Linux" and "Virtual Machine Platform".
   - Install Ubuntu from Microsoft Store and open it.

2. In Ubuntu/WSL, install dependencies:

```bash
sudo apt update
sudo apt install -y python3 python3-pip openjdk-11-jdk git unzip zlib1g-dev libffi-dev libssl-dev build-essential libjpeg-dev libfreetype6-dev libSDL2-dev cmake
pip3 install --upgrade pip
pip3 install --upgrade cython buildozer
```

## Project files

- `main.py`: entry point that runs your `GameClient` (added).
- `buildozer.spec`: build configuration (added).
- `game.py`: your existing game.

Note: The game uses sockets. On Android, `localhost` points to the phone itself. Update `GameClient.host` to your server's IP on the same network (e.g., `192.168.x.x`) before building, or add a simple input field to set the IP.

## Build (debug APK)

Run these commands inside your project folder in Ubuntu/WSL:

```bash
# Go to your project directory (adjust path if needed)
cd /mnt/c/Users/Maurício\ Santana/Documents/curso_pygame/teste_solo

# Build debug APK
buildozer -v android debug
```

The first build downloads the Android SDK/NDK and can take time. When it finishes, your APK will be under `bin/` (e.g., `bin/jogo_online-0.1-debug.apk`).

## Install on device

1. Enable Developer Options and USB debugging on your Android device.
2. Connect via USB, then:

```bash
# Install adb if missing
sudo apt install -y adb
adb devices
adb install -r bin/jogo_online-0.1-debug.apk
```

Alternatively, share the APK and install it directly on the device.

## Troubleshooting

- Java: Use OpenJDK 11 (`openjdk-11-jdk`).
- Permissions: `android.permissions = INTERNET` is set; the app can open sockets.
- Architectures: By default we build for `armeabi-v7a` and `arm64-v8a`.
- Bootstrap: `sdl2` bootstrap is selected, required for pygame.
- First run issues: If the app can't connect, verify server IP and that the server is reachable from the device's network.

## Alternative: python-for-android (direct)

```bash
pip3 install python-for-android
p4a apk \
  --private . \
  --package=org.mauricio.jogo_online \
  --name="Jogo Online" \
  --version=0.1 \
  --bootstrap sdl2 \
  --requirements=python3,pygame \
  --permission INTERNET \
  --orientation landscape \
  --arch arm64-v8a --arch armeabi-v7a
```

Build output will be under `dist/`. Buildozer is generally simpler.
