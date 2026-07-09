from .standings_scene import StandingsScene
from setup.matrix_setup import matrix
import data.ncaa_hockey_data
from utils import data_utils

from datetime import datetime as dt
from time import sleep


class NCAAHockeyStandingsScene(StandingsScene):
    """ Standings scene for NCAA hockey (men's and women's). Contains functionality to pull standings data from the ESPN API, process as needed, and build+display images based on the result.
    This class extends the general Scene and StandingsScene classes. An object of this class type is created when the scoreboard is started.
    """

    def __init__(self, league_abrv):
        """ Defines the league as NCAAMH/NCAAWH. Used to identify the correct files when adding logos to images.
        First runs init from the generic GameScene class.

        Args:
            league_abrv (str): Abbreviation of the league for which to fetch game data (e.g., 'NCAAMH', 'NCAAWH').
        """

        super().__init__()
        self.LEAGUE = league_abrv
        self.LEAGUE_LABEL = 'MH' if league_abrv == 'NCAAMH' else 'WH' # Shorter label for the standings sidebar, leaving room for conference abbreviations.

        # Add additional colour needed.
        self.COLOURS.update({
            'sidebar_highlight': (0, 94, 184) # NCAA blue.
        })


    def display_scene(self):
        """ Displays the scene on the matrix.
        """

        # Refresh config and load to settings key.
        self.settings = data_utils.read_yaml('config.yaml')['scene_settings'][self.LEAGUE.lower()]['standings']
        self.favourite_teams = data_utils.read_yaml('config.yaml')['favourite_teams'][self.LEAGUE.lower()]

        # Get current standings data.
        self.data = {
            'standings': data.ncaa_hockey_data.get_standings(self.LEAGUE)
        }

        # If the API returned no standings data at all (e.g., in the offseason), exit without displaying anything.
        if not self.data['standings']['conference']:
            return

        # Display splash if enabled.
        if self.settings['splash']['display_splash']:
            # Build splash image, transition in, pause, transition out.
            self.build_splash_image(dt.today().date())
            self.transition_image(direction='in', image_already_combined=True)
            sleep(self.settings['splash']['splash_display_duration'])
            self.transition_image(direction='out', image_already_combined=True)

        # For each standing type that should be displayed per config.yaml, build images and display.
        for type in self.settings['display_for']:
            # Check if standings data exists for the type before trying to build images.
            standing_details = self.data['standings'].get(type)
            if standing_details:
                # Loop over each conference.
                for sub_standing_details in standing_details.values():
                    self.build_standings_image(sub_standing_details)
                    self.display_standing_images()


    def display_standing_images(self):
        """ Displays standing images on the matrix w/ configured transitions.
        """

        self.transition_image(direction='in')
        self.scroll_standings_image()
        self.transition_image(direction='out', image_already_combined=False)
