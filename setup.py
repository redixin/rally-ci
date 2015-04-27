from setuptools import setup, find_packages

setup(
    name="rallyci",
    version="0.1.dev",
    data_files=[("/etc/rally-ci/", ["etc/sample-config.yaml",])],
    packages=find_packages(),
    install_requires=["pyyaml", "websockets"],
    entry_points={"console_scripts": ["rallyci = rallyci.daemon:run"]}
)
