import os
from os.path import join

from pythonforandroid.recipe import CompiledComponentsPythonRecipe
from pythonforandroid.toolchain import current_directory


class Pygame2Recipe(CompiledComponentsPythonRecipe):
    """
    Recipe to build apps based on SDL2-based pygame-ce.
    Some pygame-ce functionality may be untested on Android.
    """

    version = "2.5.7"
    url = "https://github.com/pygame-community/pygame-ce/archive/{version}.tar.gz"

    site_packages_name = "pygame-ce"
    name = "pygame-ce"

    depends = [
        "sdl2",
        "sdl2_image",
        "sdl2_mixer",
        "sdl2_ttf",
        "setuptools",
        "cython",
        "jpeg",
        "png",
    ]

    # Makes Cython importable by the hostpython3 interpreter that runs
    # `setup.py build_ext` during cross-compilation (fixed the original
    # "You need cython" error).
    hostpython_prerequisites = ["Cython<3.1"]

    call_hostpython_via_targetpython = False
    install_in_hostpython = False

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)

        with current_directory(self.get_build_dir(arch.arch)):
            # pygame-ce ships a pyproject.toml that declares meson-python as
            # its build backend. That's used for normal PyPI wheel builds,
            # but meson-python's setup step runs a compiler "sanity check"
            # that *executes* a freshly compiled test binary -- which fails
            # here because we're cross-compiling arm64 binaries and the
            # x86_64 CI host can't run them.
            #
            # pygame-ce's legacy setup.py (which builds everything
            # successfully via `build_ext` below, with no involvement from
            # pyproject.toml at all) doesn't have this problem. Removing
            # pyproject.toml makes pip fall back to that legacy path for the
            # later `pip install .` step too -- with no extra CLI flags
            # needed anywhere, so nothing leaks into the build_ext call.
            if os.path.exists("pyproject.toml"):
                os.rename("pyproject.toml", "pyproject.toml.disabled")

            setup_template = open(
                join("buildconfig", "Setup.Android.SDL2.in")
            ).read()

            env = self.get_recipe_env(arch)
            env["ANDROID_ROOT"] = join(self.ctx.ndk.sysroot, "usr")

            png = self.get_recipe("png", self.ctx)
            png_lib_dir = join(png.get_build_dir(arch.arch), ".libs")
            png_inc_dir = png.get_build_dir(arch)

            jpeg = self.get_recipe("jpeg", self.ctx)
            jpeg_inc_dir = jpeg_lib_dir = jpeg.get_build_dir(arch.arch)

            sdl_mixer_includes = ""
            sdl2_mixer_recipe = self.get_recipe("sdl2_mixer", self.ctx)
            for include_dir in sdl2_mixer_recipe.get_include_dirs(arch):
                sdl_mixer_includes += f"-I{include_dir} "

            sdl_image_includes = ""
            sdl2_image_recipe = self.get_recipe("sdl2_image", self.ctx)
            for include_dir in sdl2_image_recipe.get_include_dirs(arch):
                sdl_image_includes += f"-I{include_dir} "

            setup_file = setup_template.format(
                sdl_includes=(
                    " -I"
                    + join(self.ctx.bootstrap.build_dir, "jni", "SDL", "include")
                    + " -L"
                    + join(self.ctx.bootstrap.build_dir, "libs", str(arch))
                    + " -L"
                    + png_lib_dir
                    + " -L"
                    + jpeg_lib_dir
                    + " -L"
                    + arch.ndk_lib_dir_versioned
                ),
                sdl_ttf_includes="-I"
                + join(self.ctx.bootstrap.build_dir, "jni", "SDL2_ttf"),
                sdl_image_includes=sdl_image_includes,
                sdl_mixer_includes=sdl_mixer_includes,
                jpeg_includes="-I" + jpeg_inc_dir,
                png_includes="-I" + png_inc_dir,
                freetype_includes="",
            )

            open("Setup", "w").write(setup_file)

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)
        env["USE_SDL2"] = "1"
        env["PYGAME_CROSS_COMPILE"] = "TRUE"
        env["PYGAME_ANDROID"] = "TRUE"
        return env


recipe = Pygame2Recipe()
