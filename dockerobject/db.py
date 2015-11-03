#   Copyright 2015 Intigua
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from dockerobject import DockerObject, RunCommandHelper
import time

class DbObject(DockerObject):

    def get_connection_params(self):
        """
        return (host, port, db_name, user, password)
        """
        raise NotImplementedError()

    def wait_for_container(self):
        host, port, database, user, password =  self.get_connection_params()
        port = int(port)
        # todo: add timeout
        while not self.check_port_open(port):
            time.sleep(1)
        # give the db a chance to init, since this is a naive test
        time.sleep(2)

class MySql(DbObject):
    def __init__(self):
        super(MySql, self).__init__(repo="mysql")
        self.logger = self.logger.getChild('mysql')
        self.user = "mysql"
        self.password = "password"
        self.db = "db"
        self.port = 3306
        self.add_port_binding(self.port)
        self.add_environment('MYSQL_USER', self.user)
        self.add_environment('MYSQL_PASSWORD', self.password)
        self.add_environment('MYSQL_DATABASE', self.db)
        self.add_environment('MYSQL_ROOT_PASSWORD', self.random_password())

    def get_user(self):
        return self.user

    def get_password(self):
        return self.password

    def get_db(self):
        return self.db

    def __check_mysql_alive(self, host, port, database, user, password):
        if not self.check_port_open(self.port):
            return False
        # test that mysql can connect to the db server
        time.sleep(2)
        return True

    def wait_for_container(self):
        host, port, database, user, password =  self.get_connection_params()
        port = int(port)
        # todo: add timeout
        while not self.__check_mysql_alive(host, port, database, user, password):
            time.sleep(1)

    def run_help_command(self, helper):
        if self.should_start():
            self.start()

        with helper:
            helper.start()
            if helper.wait(5*60) != 0:
                error = self.client.attach(container=helper.get_container(), stdout=True, stderr=True, stream=False, logs=True)
                self.logger.error("Error running helper command. output: %s",  error)
                raise RuntimeError("Failed to run command for mysql. exitcode: %s" % helper.get_exit_code())

    def upload_dump(self, dumpfile):
        dumpfile = os.path.abspath(dumpfile)
        # do balagan
        binds = {dumpfile : {"ro":True, "bind" :"/tmp/dumpfile.dmp"}}
        # based on
        command_restore = """sh -c 'exec mysql  --protocol=tcp --port=$LINKED_PORT_3306_TCP_PORT --host=$LINKED_PORT_3306_TCP_ADDR -u"$LINKED_ENV_MYSQL_USER" -p"$LINKED_ENV_MYSQL_PASSWORD"   "$LINKED_ENV_MYSQL_DATABASE" < /tmp/dumpfile.dmp'"""

        return self.run_help_command(RunCommandHelper(command_restore, self, binds))

    def download_dump(self, dumpfile):
        dumpfile = os.path.abspath(dumpfile)
        # make sure file existsm so docker won't create a directory
        with open(dumpfile, 'w'):
            pass
        # do balagan
        binds = {dumpfile : {"ro":False, "bind" :"/tmp/dumpfile.dmp"}}
        # based on
        command_dump = """sh -c 'exec mysqldump --protocol=tcp --port=$DB_PORT_3306_TCP_PORT --host=$DB_PORT_3306_TCP_ADDR -u"$LINKED_ENV_MYSQL_USER" -p"$LINKED_ENV_MYSQL_PASSWORD"   "$LINKED_ENV_MYSQL_DATABASE" > /tmp/dumpfile.dmp'"""
        return self.run_help_command(RunCommandHelper(command_dump, self, binds))

    def get_connection_params(self):
        if self.should_start():
            self.start()

        host,port = self.get_host_port(self.port)
        return (host,
                port,
                self.db,
                self.user,
                self.password
                )

    def mysql(self):
        from subprocess import call
        host, port, db, user, password =  self.get_connection_params()
        env = {"MYSQL_HOST":host, "MYSQL_TCP_PORT":str(port)}
        call(["mysql", "--protocol=tcp", "-u" + user, "-p" + password, db], env=env)

class Postgres(DockerObject):
    def __init__(self, user = "pguser", password = "pgpass", db = "pgdb"):
        super(Postgres, self).__init__(repo="postgres")
        self.user = user
        self.password = password
        self.db = db
        self.logger = self.logger.getChild('postgres')
        self.set_port_bindings({5432: ('127.0.0.1',)})
        self.add_environment('POSTGRES_USER', self.user)
        self.add_environment('POSTGRES_PASSWORD', self.password)
        self.add_environment('POSTGRES_DB', self.db)

    def get_user(self):
        return self.user

    def get_password(self):
        return self.password

    def get_db(self):
        return self.db

    def __check_postges_alive(self, host, port, database, user, password):
        try:
            import psycopg2
            try:
                conn = psycopg2.connect(host=host, port=port, database=database, user=user, password=password)
                conn.close()
                return True
            except psycopg2.OperationalError:
                return False
        except ImportError:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                # port is open, give it a second to init (lame but if you don't have psycopg2, that's the best i got.)
                time.sleep(2)
                return True
        return False

    def wait_for_container(self):
        host, port, database, user, password =  self.get_connection_params()
        port = int(port)
        # todo: add timeout
        while not self.__check_postges_alive(host, port, database, user, password):
            time.sleep(1)

    def upload_dump(self, dumpfile):
        if self.should_start():
            self.start()
        dumpfile = os.path.abspath(dumpfile)
        # do balagan
        binds = {dumpfile : {"ro":True, "bind" :"/tmp/dumpfile.dmp"}}
        # based on
        # /usr/bin/pg_restore --host 192.168.1.57 --port 5432 --username "postgres" --dbname "yu" --no-password  --verbose "/home/yuval/emc/test.dump"
        command_pg_restore = """sh -c 'exec pg_restore --host "$DB_PORT_5432_TCP_ADDR" --port "$DB_PORT_5432_TCP_PORT" --dbname "%s" /tmp/dumpfile.dmp'""" % self.get_db()
        command_pgsql = """sh -c 'exec psql  --host "$DB_PORT_5432_TCP_ADDR" --port "$DB_PORT_5432_TCP_PORT" --dbname "%s" -f /tmp/dumpfile.dmp'""" % self.get_db()
        binary_sig = "PGDMP"

        command = command_pgsql
        with open(dumpfile,"rb") as f:
            if f.read(len(binary_sig)) == binary_sig:
                command = command_pg_restore

        with PostgresHelper(self, command, binds) as tmp:
            tmp.start()
            if tmp.wait(5*60) != 0:
                error = self.client.attach(container=tmp.get_container(), stdout=True, stderr=True, stream=False, logs=True)
                self.logger.error("Error running helper command. output: %s",  error)
                raise RuntimeError("Failed to upload dump. exitcode: %s" % tmp.get_exit_code())

    def download_dump(self, dumpfile):
        if self.should_start():
            self.start()
        dumpfile = os.path.abspath(dumpfile)
        # do balagan
        binds = {dumpfile : {"ro":False, "bind" :"/tmp/dumpfile.dmp"}}
        # based on
        # /usr/bin/pg_dump --host 192.168.1.57 --port 5432 --username "postgres" --no-password  --format custom --blobs --verbose --file "/tmp/t.t" "yu"
        dump_command = """sh -c 'exec pg_dump --host "$DB_PORT_5432_TCP_ADDR" --port "$DB_PORT_5432_TCP_PORT" --dbname "%s" --format custom --blobs --verbose --file /tmp/dumpfile.dmp'""" % self.get_db()

        with PostgresHelper(self, dump_command, binds) as tmp:
            tmp.start()
            if tmp.wait(5*60) != 0:
                error = self.attach()
                self.logger.error("Error running helper command. output: %s",  error)
                raise RuntimeError("Failed to download dump. exitcode: %s" % tmp.get_exit_code())

    def get_connection_params(self):
        if self.should_start():
            self.start()

        ports = self.get_port(5432)
        return ('localhost',
                ports[0]['HostPort'],
                self.db,
                self.user,
                self.password
                )

    def psql(self):
        from subprocess import call
        host, port, db, user, password =  self.get_connection_params()
        env = {"PGPASSWORD" : password, "PGHOST":host, "PGPORT":port, "PGUSER": user, "PGDATABASE" : db}
        call(["psql"], env=env )

class PostgresHelper(Postgres):

    def __init__(self, postgres, command, binds = None):
        super(PostgresHelper, self).__init__()
        self.set_volumes(binds)
        self.add_environment("PGPASSWORD", postgres.get_password())
        self.add_environment("PGUSER", postgres.get_user())
        self.add_link("db", postgres)
        self.set_command(command)

    def wait_for_container(self):
        pass
