"""Compose the Persona B latest sheet from the six working photographs."""
import io
import pathlib
from PIL import Image, ImageDraw, ImageFont

VIEWS = (
    ('body_front.jpg', 'Front body'),
    ('face_front.jpg', 'Front face'),
    ('face_left_three_quarter.jpg', 'Left 3/4'),
    ('face_right_three_quarter.jpg', 'Right 3/4'),
    ('face_left_profile.jpg', 'Left profile'),
    ('face_right_profile.jpg', 'Right profile'),
)
WIDTH = 1680
HEIGHT = 1180
BACKGROUND = (243, 240, 232)
INK = (36, 48, 40)
MUTED = (90, 96, 88)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def _font(path, size):
    return ImageFont.truetype(path, size)


def _fit(image, box):
    fitted = image.convert('RGB')
    fitted.thumbnail(box, Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', box, (232, 232, 230))
    left = (box[0] - fitted.width) // 2
    top = (box[1] - fitted.height) // 2
    canvas.paste(fitted, (left, top))
    return canvas


def render_latest_sheet(folder):
    """Return JPEG bytes for the sheet. Reads the six view files in folder."""
    folder = pathlib.Path(folder)
    sources = {}
    for name, _label in VIEWS:
        path = folder / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('persona asset unavailable')
        with Image.open(path) as image:
            image.load()
            if image.format not in ('JPEG', 'PNG'):
                raise ValueError('invalid persona image')
            sources[name] = image.copy()
    sheet = Image.new('RGB', (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    title = _font(FONT_BOLD, 34)
    subtitle = _font(FONT, 18)
    label_font = _font(FONT, 16)
    draw.text((40, 32), 'PERSONA B · LATEST', fill=INK, font=title)
    draw.text((40, 82), 'Adult 21  ·  very attractive, delicate, elegant face  ·  basic ivory tee, charcoal trousers, dark flats', fill=MUTED, font=subtitle)
    body_box = (500, 860)
    cell = (340, 400)
    body = _fit(sources['body_front.jpg'], body_box)
    sheet.paste(body, (40, 140))
    draw.text((40, 1012), 'Front body', fill=INK, font=label_font)
    slots = (
        ('face_front.jpg', (580, 140)),
        ('face_left_three_quarter.jpg', (940, 140)),
        ('face_right_three_quarter.jpg', (1300, 140)),
        ('face_left_profile.jpg', (580, 600)),
        ('face_right_profile.jpg', (940, 600)),
    )
    for name, origin in slots:
        sheet.paste(_fit(sources[name], cell), origin)
        label = dict(VIEWS)[name]
        draw.text((origin[0], origin[1] + cell[1] + 10), label, fill=INK, font=label_font)
    note = _font(FONT, 16)
    note_x, note_y = 1300, 620
    draw.multiline_text((note_x, note_y), 'Working set, not locked.\n\nFace and body: Imagine 2.0.\nAngles: quality-model edits\nof the front face.\n\nOverwrite latest/ and\nrefresh this sheet.', fill=MUTED, font=note, spacing=4)
    buffer = io.BytesIO()
    sheet.save(buffer, format='JPEG', quality=90, optimize=True)
    return buffer.getvalue()


def write_latest_sheet(folder):
    folder = pathlib.Path(folder)
    target = folder / 'sheet.jpg'
    target.write_bytes(render_latest_sheet(folder))
    return target


if __name__ == '__main__':
    destination = write_latest_sheet(pathlib.Path(__file__).resolve().parent / 'base-personas' / 'persona-b' / 'latest')
    print(destination)
