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
WIDTH = 1760
HEIGHT = 1080
PAPER = (246, 243, 236)
INK = (28, 43, 36)
MUTED = (96, 104, 98)
RULE = (214, 208, 198)
CARD = (255, 252, 247)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
SWATCHES = (
    ('face_front.jpg', (0.44, 0.38), 'Skin'),
    ('face_front.jpg', (0.34, 0.34), 'Hair'),
    ('face_front.jpg', (0.40, 0.42), 'Iris'),
    ('face_front.jpg', (0.50, 0.90), 'Ivory'),
    ('body_front.jpg', (0.54, 0.70), 'Charcoal'),
    ('body_front.jpg', (0.42, 0.92), 'Flats'),
    ('face_front.jpg', (0.08, 0.08), 'Studio'),
)
LOCKS = (
    '21-year-old adult',
    'Center-part chestnut bob, warm brown eyes, light freckles',
    'Slight closed-mouth smile, lifted nose, fine-boned face',
    'Ivory crew tee, charcoal trousers, dark closed flats',
    'No jewelry. Light gray studio. Noticeable hourglass.',
)


def _font(path, size):
    return ImageFont.truetype(path, size)


def _sample(image, xy):
    pixel = image.convert('RGB').getpixel((
        min(image.width - 1, max(0, int(image.width * xy[0]))),
        min(image.height - 1, max(0, int(image.height * xy[1]))),
    ))
    return pixel


def _trim_studio(image):
    """Crop to the figure. The studio is a gradient, so each row uses its own edge color."""
    rgb = image.convert('RGB')
    pixels = rgb.load()
    width, height = rgb.size
    min_x, min_y, max_x, max_y = width, height, 0, 0
    for y in range(0, height, 2):
        background = tuple((pixels[8, y][channel] + pixels[width - 9, y][channel]) // 2 for channel in range(3))
        for x in range(0, width, 2):
            pixel = pixels[x, y]
            if sum(abs(pixel[channel] - background[channel]) for channel in range(3)) > 40:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x <= min_x or max_y <= min_y:
        return rgb
    return rgb.crop((
        max(0, min_x - 28),
        max(0, min_y - 16),
        min(width, max_x + 29),
        min(height, max_y + 20),
    ))


def _contain(image, box, fill):
    fitted = image.convert('RGB')
    fitted.thumbnail(box, Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', box, fill)
    canvas.paste(fitted, ((box[0] - fitted.width) // 2, (box[1] - fitted.height) // 2))
    return canvas


def _cover(image, box):
    fitted = image.convert('RGB')
    scale = max(box[0] / fitted.width, box[1] / fitted.height)
    size = (max(box[0], round(fitted.width * scale)), max(box[1], round(fitted.height * scale)))
    fitted = fitted.resize(size, Image.Resampling.LANCZOS)
    left = (fitted.width - box[0]) // 2
    top = max(0, (fitted.height - box[1]) // 5)
    if top + box[1] > fitted.height:
        top = fitted.height - box[1]
    return fitted.crop((left, top, left + box[0], top + box[1]))


def _place(sheet, image, origin):
    x, y = origin
    if x < 0 or y < 0 or x + image.width > WIDTH or y + image.height > HEIGHT:
        raise ValueError('sheet image overflow')
    sheet.paste(image, origin)
    ImageDraw.Draw(sheet).rectangle(
        (x, y, x + image.width - 1, y + image.height - 1),
        outline=(255, 255, 255),
    )


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

    sheet = Image.new('RGB', (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(sheet)
    title = _font(FONT_BOLD, 26)
    eyebrow = _font(FONT, 12)
    sub = _font(FONT, 14)
    label_font = _font(FONT, 12)
    lock_font = _font(FONT, 14)

    draw.text((28, 24), 'PERSONA B', fill=INK, font=title)
    status = 'LATEST   ·   NOT LOCKED'
    draw.text((WIDTH - 28 - draw.textlength(status, font=eyebrow), 32), status, fill=MUTED, font=eyebrow)
    draw.text((28, 58), 'Elegant, beautiful, gorgeous, stunning, refined, lovely', fill=MUTED, font=sub)
    draw.text((28, 78), 'Slight smile, lifted nose, delicate, fine-boned, hourglass', fill=MUTED, font=sub)
    draw.line((28, 104, WIDTH - 28, 104), fill=RULE, width=1)

    body_fill = _sample(sources['body_front.jpg'], (0.06, 0.06))
    trimmed = _trim_studio(sources['body_front.jpg'])
    body_width = 520
    body_height = min(900, round(body_width * trimmed.height / trimmed.width))
    _place(sheet, _contain(trimmed, (body_width, body_height), body_fill), (28, 116))
    draw.text((28, 116 + body_height + 8), 'FRONT BODY', fill=INK, font=label_font)

    _place(sheet, _cover(sources['face_front.jpg'], (540, 660)), (562, 116))
    draw.text((562, 784), 'FRONT FACE', fill=INK, font=label_font)

    angle_names = (
        'face_left_three_quarter.jpg',
        'face_right_three_quarter.jpg',
        'face_left_profile.jpg',
        'face_right_profile.jpg',
    )
    angle = 300
    for index, name in enumerate(angle_names):
        column, row = index % 2, index // 2
        origin = (1116 + column * (angle + 14), 116 + row * (angle + 26))
        _place(sheet, _cover(sources[name], (angle, angle)), origin)
        draw.text((origin[0], origin[1] + angle + 6), dict(VIEWS)[name].upper(), fill=INK, font=label_font)

    card = (562, 816, WIDTH - 28, 1048)
    draw.rectangle(card, fill=CARD, outline=RULE)
    draw.text((582, 832), 'WORKING LOCKS', fill=INK, font=label_font)
    for index, line in enumerate(LOCKS):
        draw.text((582, 856 + index * 22), line, fill=MUTED, font=lock_font)

    chip = 16
    for index, (name, xy, label) in enumerate(SWATCHES):
        column, row = index // 4, index % 4
        cursor = 1180 + column * 260
        chip_y = 856 + row * 28
        color = _sample(sources[name], xy)
        draw.rectangle((cursor, chip_y, cursor + chip, chip_y + chip), fill=color, outline=RULE)
        draw.text((cursor + chip + 8, chip_y + 1), label, fill=MUTED, font=label_font)
    note = 'Angles follow the front face. The body matches by description, not as a pixel lock.'
    draw.text((582, 1012), note, fill=MUTED, font=eyebrow)
    buffer = io.BytesIO()
    sheet.save(buffer, format='JPEG', quality=92, optimize=True)
    return buffer.getvalue()


def write_latest_sheet(folder):
    folder = pathlib.Path(folder)
    target = folder / 'sheet.jpg'
    target.write_bytes(render_latest_sheet(folder))
    return target


if __name__ == '__main__':
    destination = write_latest_sheet(pathlib.Path(__file__).resolve().parent / 'base-personas' / 'persona-b' / 'latest')
    print(destination)
