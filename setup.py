# encoding: utf-8
from setuptools import setup

def readme():
    """Import README for use as long_description."""
    with open("README.rst") as f:
        return f.read()

version = "0.1.4"

setup(
    name="vantetider_scraper",
    version=version,
    description="A scraper of statistical data from Vantetider.se built on top of Statscraper.",
    long_description=readme(),
    url="https://github.com/jplusplus/vantetider-scraper",
    author="Jens Finnäs",
    author_email="jens.finnas@gmail.com",
    license="MIT",
    packages=["vantetider"],
    zip_safe=False,
    install_requires=[
        "requests",
        "requests_cache",
        "BeautifulSoup",
    ],
    test_suite="nose.collector",
    tests_require=["nose"],
    include_package_data=True,
    download_url="https://github.com/jplusplus/vantetider-scraper/archive/%s.tar.gz"
                 % version,
)
