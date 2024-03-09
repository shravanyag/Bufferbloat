import http.server
import socketserver

class CS144Handler(http.server.SimpleHTTPRequestHandler):

    # Disable logging DNS lookups
    def address_string(self):
        return str(self.client_address[0])


PORT = 80

Handler = CS144Handler
httpd = socketserver.TCPServer(("", PORT), Handler)
print ("Server1: httpd serving at port", PORT)
httpd.serve_forever()
