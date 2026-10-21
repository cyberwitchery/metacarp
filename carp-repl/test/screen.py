"""Small VT screen model for assertions against visible PTY state."""
import codecs
import re
import unicodedata


class Screen:
    def __init__(self, rows=24, columns=80):
        self.rows, self.columns = rows, columns
        self.cells = [[(" ", (False, False, None)) for _ in range(columns)] for _ in range(rows)]
        self.row = self.column = 0
        self.bold = self.italic = False
        self.foreground = None
        self.wrap = False
        self.pending = ""
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")

    def resize(self, rows, columns):
        blank = (" ", (False, False, None))
        self.cells = [(line[:columns] + [blank] * columns)[:columns] for line in self.cells[:rows]]
        self.cells += [[blank for _ in range(columns)] for _ in range(rows - len(self.cells))]
        self.rows, self.columns = rows, columns
        self.row, self.column = min(self.row, rows - 1), min(self.column, columns - 1)
        self.wrap = False

    def line(self, row, trimmed=True):
        text = "".join(cell[0] for cell in self.cells[row])
        return text.rstrip() if trimmed else text

    def text(self, trimmed=True):
        return "\n".join(self.line(row, trimmed) for row in range(self.rows))

    def find(self, text):
        for row in range(self.rows):
            start = self.line(row).find(text)
            if start >= 0:
                return row, start
        return None

    def newline(self):
        self.row += 1
        if self.row == self.rows:
            self.cells.pop(0)
            self.cells.append([(" ", (False, False, None)) for _ in range(self.columns)])
            self.row -= 1
        self.wrap = False

    def csi(self, parameters, command):
        if parameters.startswith("?"):
            return
        values = [int(value or 0) for value in parameters.split(";")]
        n = values[0] or 1
        if command == "m":
            for value in values:
                if value == 0:
                    self.bold = self.italic = False
                    self.foreground = None
                elif value == 1:
                    self.bold = True
                elif value == 3:
                    self.italic = True
                elif value == 22:
                    self.bold = False
                elif value == 23:
                    self.italic = False
                elif 30 <= value <= 37 or 90 <= value <= 97:
                    self.foreground = value
                elif value == 39:
                    self.foreground = None
            return
        self.wrap = False
        if command == "A":
            self.row = max(0, self.row - n)
        elif command == "B":
            self.row = min(self.rows - 1, self.row + n)
        elif command == "C":
            self.column = min(self.columns - 1, self.column + n)
        elif command == "D":
            self.column = max(0, self.column - n)
        elif command == "G":
            self.column = min(self.columns - 1, n - 1)
        elif command in ("H", "f"):
            self.row = min(self.rows - 1, n - 1)
            self.column = min(self.columns - 1, (values[1] or 1) - 1) if len(values) > 1 else 0
        elif command in ("J", "K"):
            mode = values[0]
            blank = (" ", (False, False, None))
            if command == "K":
                start, end = (0 if mode in (1, 2) else self.column), (self.column + 1 if mode == 1 else self.columns)
                self.cells[self.row][start:end] = [blank] * (end - start)
            elif mode == 2:
                self.cells = [[blank for _ in range(self.columns)] for _ in range(self.rows)]
            elif mode == 0:
                self.cells[self.row][self.column:] = [blank] * (self.columns - self.column)
                for row in range(self.row + 1, self.rows):
                    self.cells[row] = [blank] * self.columns

    def feed(self, data):
        self.pending += self.decoder.decode(data)
        while self.pending:
            if self.pending.startswith("\x1b["):
                match = re.match(r"\x1b\[([0-?]*)([ -/]*)([@-~])", self.pending)
                if not match:
                    return
                self.csi(match[1], match[3])
                self.pending = self.pending[match.end():]
                continue
            if self.pending.startswith("\x1b"):
                if len(self.pending) < 2:
                    return
                self.pending = self.pending[2:]
                continue
            char, self.pending = self.pending[0], self.pending[1:]
            if char == "\r":
                self.column, self.wrap = 0, False
            elif char == "\n":
                self.newline()
            elif char == "\b":
                self.column, self.wrap = max(0, self.column - 1), False
            elif char >= " ":
                width = 0 if unicodedata.combining(char) or unicodedata.category(char) in {"Mn", "Me", "Cf"} else 2 if unicodedata.east_asian_width(char) in "WF" else 1
                if width == 0:
                    previous = min(self.columns - 1, self.column if self.wrap else self.column - 1)
                    if previous >= 0:
                        glyph, style = self.cells[self.row][previous]
                        self.cells[self.row][previous] = (glyph + char, style)
                    continue
                if self.wrap or self.column + width > self.columns:
                    self.column = 0
                    self.newline()
                style = (self.bold, self.italic, self.foreground)
                self.cells[self.row][self.column] = (char, style)
                for offset in range(1, width):
                    self.cells[self.row][self.column + offset] = ("", style)
                self.column += width
                if self.column >= self.columns:
                    self.column, self.wrap = self.columns - 1, True
