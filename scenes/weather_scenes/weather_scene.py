from ..scene import Scene
from setup.matrix_setup import matrix, matrix_options
from utils import image_utils, data_utils
import data.weather_data

from PIL import Image, ImageDraw
from time import sleep


# Pixel-art weather icons, 12x12. Each character maps to a colour via ICON_COLOUR_LEGEND ('.' = transparent/black).
ICON_PIXEL_MAPS = {
    'clear': [ # Sun.
        '.....yy.....',
        '.y...yy...y.',
        '..y......y..',
        '....yyyy....',
        '...yyyyyy...',
        'yy.yyyyyy.yy',
        'yy.yyyyyy.yy',
        '...yyyyyy...',
        '....yyyy....',
        '..y......y..',
        '.y...yy...y.',
        '.....yy.....'
    ],
    'clear_night': [ # Crescent moon.
        '....mmm.....',
        '...mm.......',
        '..mm........',
        '.mm.........',
        '.mm.........',
        '.mm.........',
        '.mm.........',
        '.mm.........',
        '..mm........',
        '...mm....m..',
        '....mmmmmm..',
        '............'
    ],
    'partly_cloudy': [ # Sun peeking behind a cloud.
        '..y.yy.y....',
        '...yyyy.....',
        '..yyyyyy....',
        'y.yyyyyy.y..',
        '..yyyyyy....',
        '...yygggg...',
        'y...gggggg..',
        '.gggggggggg.',
        'gggggggggggg',
        '.gggggggggg.',
        '............',
        '............'
    ],
    'cloudy': [ # Cloud.
        '............',
        '............',
        '......ggg...',
        '.....ggggg..',
        '..gg.gggggg.',
        '.ggggggggggg',
        'gggggggggggg',
        'gggggggggggg',
        '.gggggggggg.',
        '............',
        '............',
        '............'
    ],
    'fog': [ # Horizontal fog banks.
        '............',
        '.gggggggg...',
        '............',
        '...gggggggg.',
        '............',
        '.gggggggg...',
        '............',
        '...gggggggg.',
        '............',
        '.gggggggg...',
        '............',
        '............'
    ],
    'rain': [ # Cloud with rain streaks.
        '....ggg.....',
        '...ggggg....',
        '.gg.gggggg..',
        'gggggggggggg',
        'gggggggggggg',
        '.gggggggggg.',
        '............',
        '..b..b..b...',
        '.b..b..b....',
        '............',
        '..b..b..b...',
        '.b..b..b....'
    ],
    'snow': [ # Cloud with snowflakes.
        '....ggg.....',
        '...ggggg....',
        '.gg.gggggg..',
        'gggggggggggg',
        'gggggggggggg',
        '.gggggggggg.',
        '............',
        '..w...w...w.',
        '............',
        'w...w...w...',
        '............',
        '..w...w...w.'
    ],
    'storm': [ # Cloud with lightning bolt.
        '....ggg.....',
        '...ggggg....',
        '.gg.gggggg..',
        'gggggggggggg',
        'gggggggggggg',
        '.gggggggggg.',
        '.....yy.....',
        '....yy......',
        '...yyyy.....',
        '.....yy.....',
        '....yy......',
        '...y........'
    ]
}


class WeatherScene(Scene):
    """ Weather scene showing current conditions and a multi-day forecast for the location set in config.yaml.
    Data comes from the free Open-Meteo API via data/weather_data.py.
    This class extends the general Scene class. An object of this class type is created when the scoreboard is started.
    """

    def __init__(self):
        """ Creates Image objects to be displayed on the matrix and ImageDraw objects allowing us to add icons, text, etc. to the images.
        First runs init from generic Scene class.
        """

        super().__init__()

        # Add additional colours needed for weather icons.
        self.COLOURS.update({
            'blue': (60, 130, 255),
            'pale_yellow': (230, 230, 180)
        })

        # Character -> colour legend used by ICON_PIXEL_MAPS.
        self.ICON_COLOUR_LEGEND = {
            'y': self.COLOURS['yellow'],
            'g': self.COLOURS['grey_light'],
            'd': self.COLOURS['grey_dark'],
            'b': self.COLOURS['blue'],
            'w': self.COLOURS['white'],
            'm': self.COLOURS['pale_yellow']
        }

        # Image objects.
        self.images = {
            'full': Image.new('RGB', (matrix_options.cols, matrix_options.rows))
        }

        # ImageDraw object associated with each of the above Image objects.
        self.draw = {
            'full': ImageDraw.Draw(self.images['full'])
        }


    def display_scene(self):
        """ Displays the scene on the matrix.
        """

        # Refresh config and load to settings key.
        self.settings = data_utils.read_yaml('config.yaml')['scene_settings']['weather']

        # Get current weather data. If unavailable (e.g., network issue), skip the scene entirely.
        weather = data.weather_data.get_weather()
        if not weather:
            return

        # Build and display the current conditions image.
        self.build_current_image(weather)
        self.transition_image(direction='in')
        sleep(self.settings['current']['display_duration'])
        self.transition_image(direction='out')

        # Build and display the forecast image if enabled in config.yaml.
        if self.settings['forecast']['display_forecast']:
            self.build_forecast_image(weather)
            self.transition_image(direction='in')
            sleep(self.settings['forecast']['display_duration'])
            self.transition_image(direction='out')


    def build_icon_image(self, icon, is_day=True, scale=1):
        """ Builds an Image of the requested weather icon.

        Args:
            icon (str): Icon name, a key of ICON_PIXEL_MAPS.
            is_day (bool, optional): If False and a night variant of the icon exists, use it. Defaults to True.
            scale (int, optional): Integer factor to scale the 12x12 icon by. Defaults to 1.

        Returns:
            Image: The icon image.
        """

        # Swap in the night variant if applicable.
        if not is_day and f'{icon}_night' in ICON_PIXEL_MAPS:
            icon = f'{icon}_night'

        # Draw the icon pixel by pixel from its pixel map.
        pixel_map = ICON_PIXEL_MAPS[icon]
        icon_image = Image.new('RGB', (12, 12))
        for row, row_str in enumerate(pixel_map):
            for col, char in enumerate(row_str):
                if char != '.':
                    icon_image.putpixel((col, row), self.ICON_COLOUR_LEGEND[char])

        # Scale up with nearest neighbour to keep hard pixel edges.
        if scale != 1:
            icon_image = icon_image.resize((12 * scale, 12 * scale), Image.NEAREST)

        return icon_image


    def add_degree_symbol(self, location, colour):
        """ Draws a small open square as a degree symbol. The Tamzen fonts don't include one.

        Args:
            location (tuple): (col, row) of the top-left of the symbol.
            colour (tuple): RGB colour to draw with.
        """

        col, row = location
        self.draw['full'].rectangle([(col, row), (col + 2, row + 2)], outline=colour)


    def build_current_image(self, weather):
        """ Builds the current conditions image. Large icon on the left, current temp and today's high/low on the right.

        Args:
            weather (dict): Weather data as returned by data.weather_data.get_weather().
        """

        current = weather['current']
        today = weather['daily'][0]

        # Add the current conditions icon, scaled 2x, on the left.
        icon_image = self.build_icon_image(current['icon'], is_day=current['is_day'], scale=2)
        self.images['full'].paste(icon_image, (2, 4))

        # Add the current temperature in a large font with a degree symbol.
        temp_str = str(current['temp'])
        self.draw['full'].text((30, 1), temp_str, font=self.FONTS['lrg_bold'], fill=self.COLOURS['white'])
        self.add_degree_symbol((30 + 8 * len(temp_str) + 1, 3), self.COLOURS['white'])

        # Add today's high/low below the current temperature.
        self.draw['full'].text((30, 17), f'H{today["hi"]}', font=self.FONTS['sm'], fill=self.COLOURS['white'])
        self.draw['full'].text((48, 17), f'L{today["lo"]}', font=self.FONTS['sm'], fill=self.COLOURS['grey_light'])

        # Add humidity and precipitation chance on the bottom row.
        self.draw['full'].text((30, 25), f'R{today["precip_pct"]}%', font=self.FONTS['sm'], fill=self.COLOURS['blue'])


    def build_forecast_image(self, weather):
        """ Builds the forecast image. One column per upcoming day: day abbreviation, icon, and high/low temps.

        Args:
            weather (dict): Weather data as returned by data.weather_data.get_weather().
        """

        # One column for each of the next 3 days (skipping today, which the current conditions image covers).
        for i, day in enumerate(weather['daily'][1:4]):
            col_origin = 2 + i * 21

            # Day abbreviation, centred in the column.
            self.draw['full'].text((col_origin + 5, -1), day['day_abrv'], font=self.FONTS['sm'], fill=self.COLOURS['grey_light'])

            # Icon.
            icon_image = self.build_icon_image(day['icon'])
            self.images['full'].paste(icon_image, (col_origin + 4, 8))

            # High and low temps side by side. Offset by text width so columns stay aligned for 3-digit temps.
            hi_str = str(day['hi'])
            lo_str = str(day['lo'])
            self.draw['full'].text((col_origin, 22), hi_str, font=self.FONTS['sm'], fill=self.COLOURS['white'])
            self.draw['full'].text((col_origin + 5 * len(hi_str) + 1, 22), lo_str, font=self.FONTS['sm'], fill=self.COLOURS['grey_dark'])


    def transition_image(self, direction):
        """ Transitions the full image in or out on the matrix. Transition style is set in config.yaml.

        Args:
            direction (str): Direction of the transition. 'in' or 'out'.
        """

        # 'Cut' transition.
        if self.settings['transition'] == 'cut':
            # Since there's no animation of any sort, an out transition is not needed. Simply display the image on the matrix.
            if direction == 'in':
                matrix.SetImage(self.images['full'])

        # 'Fade' transition.
        elif self.settings['transition'] == 'fade':
            # Define the 'fade rule', that is the steps between 0 (transparent) and 255 (opaque).
            fade = (255, -1, -15) if direction == 'in' else (0, 256, 15)

            # Loop over opacities to apply to image.
            for overlay_opacity in range(*fade):
                # Create faded image to display on matrix.
                faded_for_display_image = self.create_faded_image(self.images['full'], overlay_opacity)

                # Display and sleep for a short time to pace the animation.
                matrix.SetImage(faded_for_display_image)
                sleep(0.025)

            # Hold a moment with nothing displayed after fading out.
            if direction == 'out':
                sleep(0.2)

        # 'Modern' transition.
        elif self.settings['transition'] == 'modern':
            # Define the 'fade rule', that is the steps between 0 (transparent) and 255 (opaque).
            fade = (255, -1, -15) if direction == 'in' else (0, 256, 15)

            # Keep a copy of the built image, as the full image is rebuilt with offsets during the animation.
            combined_image = self.images['full'].copy()

            # Determine the horizontal movement for each animation frame.
            if direction == 'in':
                col_offsets = range(-len(range(*fade)) + 1, 1, 1)
            else:
                col_offsets = range(0, len(range(*fade)), 1)

            # Loop over opacities to apply to image and horizontal movement via col_offset.
            for overlay_opacity, col_offset in zip(range(*fade), col_offsets):
                # Rebuild full image with offsets. Will first need to clear the image. This will also ensure there's no artifacts between loops of animation.
                image_utils.clear_image(self.images['full'], self.draw['full'])
                self.images['full'].paste(combined_image, (col_offset, 0))

                # Create faded image to display on matrix.
                faded_for_display_image = self.create_faded_image(self.images['full'], overlay_opacity)

                # Display and sleep for a short time to pace the animation.
                matrix.SetImage(faded_for_display_image)
                sleep(0.025)

            # Hold a moment with nothing displayed.
            if direction == 'out':
                sleep(0.2)

        # On way out of 'out' transitions, reset the image to black for the next image build.
        if direction == 'out':
            image_utils.clear_image(self.images['full'], self.draw['full'])
