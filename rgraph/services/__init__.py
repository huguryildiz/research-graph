"""Provider-neutral services shared by the CLI and the local browser interface.

Every rule that decides *what may happen* lives here rather than in a command or
in an HTTP handler, so the terminal path and the browser path cannot drift into
two different contracts. Modules in this package never print and never touch
`rich`; they return data.
"""
