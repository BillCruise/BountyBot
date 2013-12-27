import webapp2

MAIN_PAGE_HTML = """\
<html>
  <head>
    <title>Bounty Bot</title>
  </head>
  <body>
    <h3>Bounty Bot</h3>
    <p>This is the home of <a href="https://twitter.com/BountyBot">@BountyBot</a>.
       I'm a Twitter 'bot that posts links to bounty questions from
       <a href="http://stackoverflow.com/?tab=featured">Stack Overflow</a>.
       There's not a lot else to see here.
  </body>
</html>
"""


class MainHandler(webapp2.RequestHandler):
    def get(self):
        self.response.write(MAIN_PAGE_HTML)

app = webapp2.WSGIApplication([
    ('/', MainHandler)
], debug=True)
