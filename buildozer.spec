[app]
title = Survivor Rush
package.name = survivorrush
package.domain = com.survivorrush
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,wav,txt
version = 0.1
requirements = python3,pygame-ce
orientation = landscape
fullscreen = 1
android.api = 36
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.local_recipes = ./p4a-recipes

[buildozer]
log_level = 2
warn_on_root = 1
