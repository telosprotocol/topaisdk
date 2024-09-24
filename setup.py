from setuptools import setup, find_packages

setup(
    name="topaisdk",
    version="0.1.2",
    author="error.ding",
    author_email="error.ding@uptech.ai",
    description="topai python sdk",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    url="http://github.com/topailab",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=["ray==2.34.0"],
    classifiers=[
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
