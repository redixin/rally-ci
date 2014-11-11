from setuptools import setup, find_packages

setup(
        name = "rallyci",
        version = "0.1.dev",
        packages = ["rallyci"],
        install_requires = ["mako", "pyyaml"],
        entry_points = {"console_scripts": ["rallyci = rallyci.daemon"]}
)
