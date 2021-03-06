import os
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
make_abs = lambda fn: os.path.join(here, fn)


def parse_requirments(fn, dependency_links):
    requirements = []

    if not os.path.exists(fn):
        return requirements, dependency_links

    with open(fn, 'r') as f:
        for dep in f:
            dep = dep.strip()
            # need to make github requirements work with
            # setuptools like it would work with `pip -r`
            # URLs will not work, so we transform them to
            # dependency_links and requirements
            if dep.startswith('git+'):
                dependency_links.append(dep)
                _, dep = dep.rsplit('#egg=', 1)
                dep = dep.replace('-', '==', 1)
            requirements.append(dep)

    return requirements, dependency_links


requirements, dependency_links = parse_requirments(
    make_abs('requirements.txt'), [])


setup(
    name='taal',
    packages=find_packages(exclude=['tests', 'tests.*']),
    version='0.8.2',
    author='onefinestay',
    author_email='engineering@onefinestay.com',
    url='https://github.com/onefinestay/taal',
    install_requires=requirements,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Topic :: Software Development",
        "Topic :: Utilities",
    ],
    description='Model translations',
    long_description=open(make_abs('README.rst')).read(),
    include_package_data=True,
    zip_safe=True,
)
