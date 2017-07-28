from setuptools import setup


setup(
    name='grow-ext-build-server',
    version='1.0.0',
    license='MIT',
    author='Grow Authors',
    author_email='hello@grow.io',
    include_package_data=False,
    packages=[
        'grow_build_server',
    ],
    install_requires=[
        'bs4',
        'google-api-python-client',
        'google-auth',
        'jinja2',
        'premailer',
        'requests',
        'requests-toolbelt',
    ],
)
