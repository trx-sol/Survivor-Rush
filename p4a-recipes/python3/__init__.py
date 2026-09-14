from pythonforandroid.recipes.python3 import Python3Recipe


class CustomPython3Recipe(Python3Recipe):
    name = "python3"
    version = "3.12.14"

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)
        env["PYTHON_DISABLE_MODULES"] = "grp"
        return env


recipe = CustomPython3Recipe()
