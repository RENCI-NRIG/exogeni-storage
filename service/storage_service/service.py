#!/usr/bin/python
#
# UvA ExoGENI Storage Service
#
# Sources:
# http://moreit.eu/2013/06/extending-python-simplexmlrpcserver-with-authentication/
# http://code.activestate.com/recipes/496786-simple-xml-rpc-server-over-https/
# http://rzemieniecki.wordpress.com/2012/08/10/quick-solution-to-ssl-in-simplexmlrpcserver-python-2-6-and-2-7/
# Paul Ruth's neuca-agent code (for option-parsing and foreground mode)

import SocketServer, BaseHTTPServer, SimpleXMLRPCServer
import socket, ssl, os, signal, sys
import logging, logging.config
import ConfigParser
from gevent import Timeout
from gevent.subprocess import Popen, PIPE
from setproctitle import setproctitle
from concurrent.futures import ThreadPoolExecutor

import storage_service as ss

CONFIG = ConfigParser.SafeConfigParser()
CONFIG.add_section('network')
CONFIG.add_section('runtime')
CONFIG.add_section('logging')
CONFIG.set('network', 'listen-host', ss.__ListenHost__)
CONFIG.set('network', 'listen-port', ss.__ListenPort__)
CONFIG.set('runtime', 'passwd-file', ss.__ConfDir__ + '/' + ss.__PasswdFile__)
CONFIG.set('runtime', 'key-file', ss.__ConfDir__ + '/' + ss.__KeyFile__)
CONFIG.set('runtime', 'cert-file', ss.__ConfDir__ + '/' + ss.__CertFile__)
CONFIG.set('runtime', 'script-directory', ss.__ScriptDir__)
CONFIG.set('runtime', 'script-file', ss.__StorageManagementScript__)
CONFIG.set('runtime', 'script-timeout', ss.__StorageManagementScriptTimeout__)
CONFIG.set('runtime', 'pid-directory', ss.__PidDir__)
CONFIG.set('runtime', 'pid-file', ss.__PidFile__)
CONFIG.set('runtime', 'pool-workers', ss.__PoolWorkers__)

LOGGER = 'storage_service'


class ThreadPoolMixIn(SocketServer.ThreadingMixIn):
    def process_request(self, request, client_address):
        try:
            self.pool.submit(self.process_request_thread, request, client_address)
        except:
            self.handle_error(request, client_address)
            self.close_request(request)


class SecureXMLRPCServer(ThreadPoolMixIn, BaseHTTPServer.HTTPServer, SimpleXMLRPCServer.SimpleXMLRPCDispatcher):
    def __init__(self, server_address, HandlerClass, logRequests=True):
        self.logRequests = logRequests
        self.users = None
        self.pool = ThreadPoolExecutor(max_workers = CONFIG.getint('runtime', 'pool-workers'))

        try:
            # Python >= 2.5
            SimpleXMLRPCServer.SimpleXMLRPCDispatcher.__init__(self, False, None)
        except TypeError:
            # Python < 2.5
            SimpleXMLRPCServer.SimpleXMLRPCDispatcher.__init__(self)
       
        SocketServer.BaseServer.__init__(self, server_address, HandlerClass)
 
        self.socket = ssl.wrap_socket(socket.socket(), server_side = True,
                                      certfile = CONFIG.get('runtime', 'cert-file'),
                                      keyfile = CONFIG.get('runtime', 'key-file'),
                                      ssl_version = ssl.PROTOCOL_TLSv1)
        self.server_bind()
        self.server_activate()

    def internal_shutdown(self):
        logger = logging.getLogger(LOGGER)
        logger.info("Shutdown requested; waiting for worker pool to quiesce...")
        self.pool.shutdown(wait = True)
        logger.info("Worker pool quiesced; shutting down.")
        sys.exit(0)


class SecureXMLRPCRequestHandler(SimpleXMLRPCServer.SimpleXMLRPCRequestHandler):
    def report_401(self):
        self.send_response(401)
        response = 'Authentication required.'
        self.send_header('WWW-Authenticate', 'Basic realm=\"Authentication required.\"')
        self.send_header("Content-type", "text/plain")
        self.send_header("Content-length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def setup(self):
        self.connection = self.request
        self.rfile = socket._fileobject(self.request, "rb", self.rbufsize)
        self.wfile = socket._fileobject(self.request, "wb", self.wbufsize)

    def do_POST(self):
        logger = logging.getLogger(LOGGER)
        logger.debug("Performing authentication checks...")
        if not self.checkAuthorization():
            logger.debug("Authentication failed.")
            self.report_401()
        else:
            logger.debug("Authentication succeeded.")
            try:
                data = self.rfile.read(int(self.headers["content-length"]))
                response = self.server._marshaled_dispatch(
                        data, getattr(self, '_dispatch', None)
                    )
            except: 
                self.send_response(500)
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-type", "text/xml")
                self.send_header("Content-length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
            
    def checkAuthorization(self):
        logger = logging.getLogger(LOGGER)
        header = self.headers.getheader('Authorization')
        if header != None:
            authType, authData = header.split(' ')
            if authType == 'Basic':
                from base64 import b64decode
                authData_decoded = b64decode(authData)
                user, password = authData_decoded.split(':')
                logger.debug("Checking authentication for user: %s", user)
                return self.server.users.verify(user, password)
        return False


class StorageService():
    def __init__(self):
        self.stdin_path = '/dev/null'
        self.stdout_path = '/dev/null'
        self.stderr_path = '/dev/null'
        self.pidfile_path = (CONFIG.get('runtime', 'pid-directory') +
                             '/' +
                             CONFIG.get('runtime', 'pid-file'))
        self.pidfile_timeout = 10
        self.logger = logging.getLogger(LOGGER)
        self.scriptfile_path = (CONFIG.get('runtime', 'script-directory') +
                                '/' +
                                CONFIG.get('runtime', 'script-file'))
        self.script_timeout = CONFIG.getint('runtime', 'script-timeout')

    # Create iSCSI target.
    def create(self, usernames, passwords, target_iqn, target_lun, size, initiator_iqn_list):
        # NB: initiator_iqn_list needs to be a comma separated list of initiator iqn strings
        self.logger.debug("Preparing to execute create()")
        timeout = Timeout(self.script_timeout)
        process = Popen(self.scriptfile_path +
                        " -c -q" +
                        " -u " + usernames +
                        " -p " + passwords +
                        " -s " + size +
                        " -m " + target_lun +
                        " -t " + target_iqn +
                        " -i " + initiator_iqn_list,
                        stdout=PIPE, shell=True)

        output = "Create operation exceeded execution timeout.\n"
        returncode = 1
        timeout.start()
        try:
            output = process.communicate()[0]
            returncode = process.returncode
        except Timeout:
            process.kill()
            self.logger.warn("Process %s servicing create() " +
                             "exceeded execution timeout and was terminated.",
                             process.pid)
            if process.returncode is not None:
                returncode = process.returncode
        finally:
            timeout.cancel()
        return [output, returncode]

    # Delete iSCSI target.
    def delete(self, name):
        self.logger.debug("Preparing to execute delete()")
        timeout = Timeout(self.script_timeout)
        process = Popen(self.scriptfile_path +
                        " -d -q" +
                        " -n " + name,
                        stdout=PIPE, shell=True)

        output = "Delete operation exceeded execution timeout.\n"
        returncode = 1
        timeout.start()
        try:
            output = process.communicate()[0]
            returncode = process.returncode
        except Timeout:
            process.kill()
            self.logger.warn("Process %s servicing delete() " +
                             "exceeded execution timeout and was terminated.",
                             process.pid)
            if process.returncode is not None:
                returncode = process.returncode
        finally:
            timeout.cancel()
        return [output, returncode]

    def run(self):
        import gevent.monkey
        gevent.monkey.patch_all()

        server_address = (CONFIG.get('network', 'listen-host'),
                          CONFIG.getint('network', 'listen-port'))
        self.server = SecureXMLRPCServer(server_address, SecureXMLRPCRequestHandler)

        # Set process name
        setproctitle('storage_serviced')

        # Register functions
        self.server.register_function(self.create, 'create')
        self.server.register_function(self.delete, 'delete')

        # Read users file
        from passlib.apache import HtpasswdFile
        passwd_file = CONFIG.get('runtime', 'passwd-file')
        try:
            self.server.users = HtpasswdFile(passwd_file)
        except:
            self.logger.error("Could not open authentication file %s"
                              % passwd_file)

        self.logger.info("Storage service running as PID %d" % os.getpid())
        self.logger.info("Listening on %s:%d" % server_address)
        signal.signal(signal.SIGTERM, self.stop_handler)
        self.server.serve_forever()

    def stop_handler(self, signum, frame):
        try:
            self.server
        except:
            self.logger.error("Calling stop() before run() has been called is undefined! Exiting...")
            sys.exit(1)
        else:
            self.server.internal_shutdown()

    def stop(self):
        self.stop_handler(None, None)


def main():
    from optparse import OptionParser

    usagestr = "Usage: %prog start|stop|restart [options]"
    parser = OptionParser(usage=usagestr)
    parser.add_option("-f", "--foreground", dest="foreground",
                      action="store_true", default=False,
                      help="Run the storage service in foreground (useful for debugging).")
    parser.add_option("-c", "--conffile", dest="config_file", metavar="CONFFILE",
                      help="Read configuration from file CONFFILE, rather than the default location.")
    parser.add_option("-l", "--logconffile", dest="log_config_file", metavar="LOGCONFFILE",
                      help="Read configuration from file LOGCONFFILE, rather than the default location.")

    options, args = parser.parse_args()

    if len(args) != 1:
        parser.print_help()
        sys.exit(1)

    initial_log_location = '/dev/tty'
    try:
        logfd = open(initial_log_location, 'r')
    except:
        initial_log_location = '/dev/null'
    else:
        logfd.close()

    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    logging.basicConfig(format=log_format, filename=initial_log_location)

    config_file = ss.__ConfDir__ + '/' + ss.__ConfFile__
    if options.config_file:
        config_file = options.config_file

    try:
        files_read = CONFIG.read(config_file)
        if len(files_read)  == 0:
            logging.warn("Configuration file could not be read; proceeding with default settings.")
    except Exception, e:
        logging.error("Unable to parse configuration file \"%s\": %s"
                      % (config_file, str(e)))
        logging.error("Exiting...")
        sys.exit(1)

    log_config_file = ss.__ConfDir__ + '/' + ss.__LogConfFile__
    if options.log_config_file:
        log_config_file = options.log_config_file

    try:
        logging.config.fileConfig(log_config_file)
    except Exception, e:
        logging.error("Unable to parse logging configuration file \"%s\": %s"
                      % (log_config_file, str(e)))
        logging.error("Exiting...")
        sys.exit(1)

    from daemon import runner, pidlockfile

    service = StorageService()
    daemon_runner = runner.DaemonRunner(service)

    global LOGGER
    if options.foreground:
        LOGGER = 'storage_service_console'
        service_logger = logging.getLogger(LOGGER)
        service.logger = service_logger

        if runner.is_pidfile_stale(daemon_runner.pidfile):
            daemon_runner.pidfile.break_lock()

        from lockfile import LockTimeout
        try:
            daemon_runner.pidfile.acquire()
        except LockTimeout:
            service_logger.error("PID file %(service.pidfile_path)r already locked. Exiting..." % vars())
            sys.exit(1)

        try:
            service_logger.info("Running service in foreground mode. Press Control-c to stop.")
            service.run()
        except KeyboardInterrupt:
            service_logger.info("Stopping service at user request (via keyboard interrupt). Exiting...")
            service.stop()
            sys.exit(0)
    else:
        service_logger = logging.getLogger(LOGGER)

        if args[0] == 'start':
            sys.argv = [sys.argv[0], 'start']
        elif args[0] == 'stop':
            sys.argv = [sys.argv[0], 'stop']
        elif args[0] == 'restart':
            sys.argv = [sys.argv[0], 'restart']
        else:
            parser.print_help()
            sys.exit(1)

        service_logger.propagate = False

        for handler in service_logger.handlers:
            daemon_runner.daemon_context.files_preserve = [ handler.stream, ]

        try:
            service_logger.info("Administrative operation: %s" % args[0])
            daemon_runner.do_action()
        except runner.DaemonRunnerStopFailureError, drsfe:
            service_logger.propagate = True
            service_logger.error("Unable to stop service; reason was: %s" % str(drsfe))
            service_logger.error("Exiting...")
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
