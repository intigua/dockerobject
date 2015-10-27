from dockerobject import DockerObject
import time
import requests

class WebObject(DockerObject):
    def __init__(self, port, *args, **kwargs):
        super(WebObject, self).__init__(*args, **kwargs)
        self.port = port
        self.add_port_binding(self.port)
        # not using expose_all_ports intentionally

    def get_url(self):
        if self.should_start():
            self.start(wait=False)
        ports = self.get_port(self.port)
        host, port = 'localhost', ports[0]['HostPort']
        return "http://%s:%d" % (host, int(port))

    def wait_for_sever(self, timeout = 60):
        url = self.get_url()
        self.logger.debug('Waiting for web service to start')
        timeout_time = time.time() + timeout
        while time.time() < timeout_time:
            try:
                while 200 != requests.get(url).status_code:
                    time.sleep(1)
                return
            except requests.exceptions.ConnectionError:
                time.sleep(1)

        raise RuntimeError('Timeout waiting for web service')

    def wait_for_container(self):
        self.wait_for_sever()

class Nginx(WebObject):
    def __init__(self):
        super(Nginx, self).__init__(port = 80, repo="nginx")
        self.logger = self.logger.getChild('nignx')
