from setuptools import setup

version = '1.1.0'

with open('README.rst', 'r') as file:
    long_description = file.read()

setup(name='bionic-falcon',
      version=version,
      description='Automate CRUD actions with a Falcon API',
      long_description=long_description,
      url='https://github.com/enodoscore/falcon-autocrud',
      author='Gary Monson, Cami McCarthy',
      author_email='camilla@enodoinc.com',
      license='MIT',
      classifiers=[
          'Development Status :: 4 - Beta',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.4',
          'Topic :: Database :: Front-Ends',
          'Topic :: Internet :: WWW/HTTP',
          'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
          'Topic :: Internet :: WWW/HTTP :: WSGI :: Middleware',
      ],
      keywords='falcon crud rest database',
      packages=['bionic_falcon'],
      install_requires=[
          'falcon >= 2.0.0',
          'jsonschema',
          'sqlalchemy',
      ],
      zip_safe=False)
