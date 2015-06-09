from setuptools import setup, find_packages

setup(
    name="rallyci",
    version="0.1.dev0",
    data_files=[
        ("etc/rally-ci/", ["etc/sample-config.yaml",
                           "etc/noop.yaml",
                           "etc/simulation-config.yaml"]),
    ],
    packages=find_packages(),
    install_requires=["pyyaml", "websockets", "aiohttp"],
    entry_points={"console_scripts": ["rally-ci = rallyci.daemon:run"]}
)
