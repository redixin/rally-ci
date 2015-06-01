from setuptools import setup, find_packages

setup(
    name="rallyci",
    version="0.1.dev0",
    data_files=[
        ("/etc/rally-ci/", ["etc/sample-config.yaml",
                            "etc/simulation-config.yaml"]),
        ("/var/lib/rally-ci/", ["resources/gerrit-sample-stream.json", ]),
    ],
    packages=find_packages(),
    install_requires=["pyyaml", "websockets"],
    entry_points={"console_scripts": ["rally-ci = rallyci.daemon:run"]}
)
