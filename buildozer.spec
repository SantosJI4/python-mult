[app]
title = Jogo Online
package.name = jogo_online
package.domain = org.mauricio
version = 0.1
source.dir = .
source.include_exts = py,json
requirements = python3,pygame,websockets
orientation = landscape
android.permissions = INTERNET
bootstrap = sdl2
android.archs = armeabi-v7a,arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 0