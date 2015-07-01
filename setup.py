from setuptools import setup, find_packages

setup(
    name="rally-ci",
    version="0.1.1a1",
    data_files=[
        ("etc/rally-ci/", ["etc/sample-config.yaml",
                           "etc/noop.yaml"]),
    ],
    packages=find_packages(),
    include_package_data=True,
    install_requires=["pyyaml", "aiohttp"],
    entry_points={"console_scripts": ["rally-ci = rallyci.daemon:run"]}
)
