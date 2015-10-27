from docker import Client
import logging
import os
import string
import random

LOGGER = 'dockeobject'

class DockerObject(object):

    def __init__(self, repo, tag = None):
        self.client = Client(base_url='unix://var/run/docker.sock', version='auto')
        self.logger = logging.getLogger(LOGGER)
        self.repo = repo
        self.tag  = tag
        self.command = None
        self.image = self.repo
        if self.tag:
            self.image = self.image + ':' + self.tag
        self.__container = None
        self.environment = {}
        self.port_bindings = None
        self.privileged = None
        self.binds = None
        self.hostname = None
        self.links = []
        # internal containers are created, started, and destryed along with this container.
        self.internal_containers = []
        self.exit_code  = None
        # login is global in docker and should not be implemented here.
        # self.login = False
        self.volumes_from = None
        self.insecure_registry = False

    def enable_debug(self):
        ch = logging.StreamHandler()
        self.logger.addHandler(ch)
        self.logger.setLevel(logging.DEBUG)

    def wait(self, timeout):
        if self.exit_code is None:
            self.logger.debug('waiting for container to end.')
            self.exit_code = self.client.wait(self.get_container(), timeout)
        return self.exit_code

    def get_exit_code(self):
        return self.exit_code

    def add_volumes_from(self, container):
        if self.volumes_from is None:
            self.volumes_from = []
        if isinstance(container, DockerObject):
            self.volumes_from.append(container.get_container())
        else:
            self.volumes_from.append(container)

    def set_volumes(self, binds):
        self.binds = binds

    def set_hostname(self, hostname):
        self.hostname = hostname

    def set_command(self, command):
        self.command = command

    def set_privileged(self, privileged):
        self.privileged = privileged

    def add_link(self, name, container, internal = False):
        if isinstance(container, DockerObject):
            self.links.append((container, name))
            if internal:
                self.internal_containers.append(container)
        else:
            raise RuntimeError("illegal argument")

    def add_environment(self, key, value):
        self.environment[key] = value

    def set_port_bindings(self, port_bindings):
        self.port_bindings = port_bindings

    def add_port_binding(self, port):
        if self.port_bindings is None:
            self.port_bindings = {}
        self.port_bindings[port] = ('0.0.0.0',)

    def expose_all_ports(self):
        self.pull_if_needed(repository=self.repo, tag=self.tag, insecure_registry = self.insecure_registry)
        image = self.client.inspect_image(image=self.image)
        ports = image["Config"]["ExposedPorts"]
        for port in ports:
            self.add_port_binding(port)

    def add_volume(self, local, container, ro=False):
        if self.binds is None:
            self.binds = {}
        local = os.path.abspath(local)
        self.binds[local] = {"ro":ro, "bind": container}

    def set_container(self, container):
        self.__container = container

    def get_container(self):
        return self.__container

    def get_tag(self):
        return self.tag

    def get_repository(self):
        return self.repo

    def create(self):
        # create only if needed
        if not self.should_create():
            return

        if self.internal_containers:
            self.logger.debug('creating linked containers')
            for c in self.internal_containers:
                c.create()

        self.pull_if_needed(repository=self.repo, tag=self.tag, insecure_registry = True)
        ports = None
        if self.port_bindings:
            ports = [k for k in self.port_bindings]
        volume_to_mount = None
        if self.binds:
            volume_to_mount = [self.binds[k]['bind'] for k in self.binds]

        container = self.client.create_container(image=self.image, hostname=self.hostname, ports=ports, environment=self.environment, volumes=volume_to_mount, command=self.command).get('Id')
        self.set_container(container)
        self.logger.debug('Container %s created %s', self.repo, container)

    def start_container(self):
        self.logger.debug('Starting container %s (%s)', self.repo, self.get_container())
        links = {}
        for container, name in self.links:
            links[container.get_container()] = name
        self.client.start(container=self.get_container(), links=links, port_bindings=self.port_bindings, privileged=self.privileged, binds=self.binds, volumes_from=self.volumes_from)

    def pull_if_needed(self, repository, tag = None, insecure_registry = False):
        images = self.client.images(name=repository)
        pull = False
        if len(images) == 0:
            self.logger.debug('Pulling: no images for %s', repository)
            pull = True
        elif tag != None:
            l = [ x['RepoTags'] for x in images ]
            tags = [ item for sublist in l for item in sublist ]
            repo_and_tag = repository + ':' + tag
            # TODO: check if tags are case sensitive
            # tags = [x.lower() for x in tags]
            # repo_and_tag = repo_and_tag.lower()
            if repo_and_tag not in tags:
                self.logger.debug('Pullin: %s not in %s', repo_and_tag, tags)
                pull = True
        if pull:
            self.logger.debug('Pulling %s', repository)
            self.client.pull(repository=repository, tag=tag, insecure_registry=insecure_registry)

    def should_create(self):
        return self.__container == None

    def destroy(self):
        if self.get_container() == None:
            return
        self.logger.debug('destroying container %s', self.repo)
        self.client.remove_container(container=self.get_container(), force=True)
        self.set_container(None)
        if self.internal_containers:
            self.logger.debug('destroying linked containers')
            for c in reversed(self.internal_containers):
                c.destroy()

    def start(self, wait = True):
        if self.should_create():
            self.create()

        if self.internal_containers:
            self.logger.debug('starting linked containers')
            for c in self.internal_containers:
                c.start(wait=True)

        self.start_container()
        self.exit_code = None
        if wait:
            self.wait_for_container()

    def stop(self):
        # do not stop linked containers. as it is not a must
        self.logger.debug('Stopping container %s', self.repo)
        self.client.stop(container=self.get_container(), timeout=2)

    def should_start(self):
        if self.should_create():
            return True
        return not self.client.inspect_container(container=self.__container)['State']['Running']

    def get_port(self, port):
        return self.client.port(container=self.get_container(), private_port=port)

    def attach(self, stdout=True, stderr=True, stream=False, logs=True):
        return self.client.attach(container=self.get_container(), stdout=stdout, stderr=stderr, stream=stream, logs=logs)

    def get_hostname(self):
        return self.client.inspect_container(container=self.__container)['Config']['Hostname']

    def get_ip(self):
        return self.client.inspect_container(container=self.__container)["NetworkSettings"]["IPAddress"]

    def inspect(self):
        return self.client.inspect_container(container=self.__container)

    def __enter__(self):
        self.create()
        return self

    def __exit__(self, type_, value_, tb):
        self.destroy()

    def __del__(self):
        self.destroy()

    def get_host_port(self, port):
        ports = self.get_port(port)
        host, port = 'localhost', ports[0]['HostPort']
        port = int(port)
        return host, port

    def check_port_open(self, port):
        host, port = self.get_host_port(port)
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            return True
        return False

    def random_password(self,size=8, chars=string.ascii_uppercase + string.ascii_lowercase + string.digits):
        # http://stackoverflow.com/questions/2257441/random-string-generation-with-upper-case-letters-and-digits-in-python
        return ''.join(random.choice(chars) for _ in range(size))

    def wait_for_container(self):
        raise NotImplementedError()

    def get_url(self):
        pass

    def browser(self):
        url = self.get_url()
        if not url:
            raise RuntimeError("url is not valid")
        os.system("xdg-open " + self.get_url())

class RunCommandHelper(DockerObject):
    
    def __init__(self, command, linked=None, binds = None):
        linked_repo = "ubuntu" if linked is None else linked.get_repository()
        linked_tag  = "14.04"  if linked is None else linked.get_tag()
        super(RunCommandHelper, self).__init__(linked_repo, linked_tag)
        if binds:
            self.set_volumes(binds)
        if linked:
            self.add_link("linked", linked)
        self.set_command(command)

    def wait_for_container(self):
        pass
