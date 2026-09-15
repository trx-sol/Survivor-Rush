import os
import re
from os.path import join

from pythonforandroid.logger import info, shprint
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

    hostpython_prerequisites = ["Cython<3.1","setuptools", "wheel"]

    call_hostpython_via_targetpython = False
    install_in_hostpython = False

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)

        with current_directory(self.get_build_dir(arch.arch)):
            # Strip pygame-ce's [build-system] table so `pip install .`
            # doesn't try to use meson-python (its compiler sanity check
            # can't execute cross-compiled arm64 binaries on the x86_64
            # CI host). setup.py's own version lookup only reads the
            # [project] table, so it's untouched.
            pyproject_path = "pyproject.toml"
            if os.path.exists(pyproject_path):
                with open(pyproject_path, "r") as f:
                    pyproject_contents = f.read()

                pyproject_contents = re.sub(
                    r"\[build-system\].*?(?=\n\[)",
                    "",
                    pyproject_contents,
                    flags=re.DOTALL,
                )

                with open(pyproject_path, "w") as f:
                    f.write(pyproject_contents)

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

    def install_python_package(self, arch, name=None, env=None, is_dir=True):
        # Override rather than using `setup_extra_args`, because that
        # attribute also gets appended to the earlier `setup.py build_ext`
        # call (which doesn't understand pip-only flags and breaks).
        #
        # `--no-use-pep517` skips pip's "get requirements to build wheel"
        # step entirely -- the step that was spinning up a fresh, isolated
        # build venv with no Cython in it and reproducing the original
        # "You need cython" error. `--no-build-isolation` reinforces that:
        # everything runs directly in hostpython3's real environment,
        # where `hostpython_prerequisites` already put Cython.
        if env is None:
            env = self.get_recipe_env(arch)
        info('Installing {} into site-packages'.format(self.name))
        with current_directory(self.get_build_dir(arch.arch)):
            shprint(
                self._host_recipe.pip, 'install', '.',
                '--compile',
                '--no-use-pep517',
                '--no-build-isolation',
                '--target', self.ctx.get_python_install_dir(arch.arch),
                _env=env,
            )


recipe = Pygame2Recipe()
