# dockerobject
Object oriented wrapper for docker-py.

Install using:
    python setup.py install

# Examples
Usage example with existing Postgres class:

    >>> from dockerobject import *
    >>> from dockerobject.db import *
    >>> p = Postgres()
    >>> p.start()
    ('localhost', u'32771', 'pgdb', 'pguser', 'pgpass')

Will start a new postgres container.

If you have psql installed, you can use it in interactive mode:

    >>> p.psql()
    psql (9.3.9, server 9.4.1)
    WARNING: psql major version 9.3, server major version 9.4.
             Some psql features might not work.
    Type "help" for help.
    pgdb=# \q
    # when variable deleted, container is destroyed
    >>> del p

Can be used with scope as well:

    with Postgres() as p:
        p.start()
        # ...
        p.download_dump("/home/yuval/dump.db")
