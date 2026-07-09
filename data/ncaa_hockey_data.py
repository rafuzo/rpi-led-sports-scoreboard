from setup.session_setup import session
from datetime import datetime as dt
from datetime import timezone as tz
from PIL import Image, ImageDraw, ImageFont
import os


# Mapping of internal league abbreviations to the slugs used by the ESPN API.
league_slugs = {
    'NCAAMH': 'mens-college-hockey',
    'NCAAWH': 'womens-college-hockey'
}

# Mapping of conference names returned by the ESPN API to shorter abbreviations that fit in the standings sidebar (max 4 chars).
conference_abbreviations = {
    'Big Ten Conference': 'B1G',
    'Western Collegiate Hockey Association': 'WCHA'
}

# Cache of team abbreviation to ESPN team ID mappings by league. Populated on first use to avoid repeated API calls.
team_ids = {}


def get_games(date, league_abrv):
    """ Loads NCAA hockey game data for the provided date.

    Args:
        date (date): Date that game data should be pulled for.
        league_abrv (str): Abbreviation of the league for which to fetch game data (e.g., 'NCAAMH', 'NCAAWH').

    Returns:
        list: List of dicts of game data.
    """

    # Create an empty list to hold the game dicts.
    games = []

    # Call the ESPN scoreboard API for the league and date specified and store the JSON results.
    url = f'https://site.api.espn.com/apis/site/v2/sports/hockey/{league_slugs[league_abrv]}/scoreboard'
    games_response = session.get(url=f"{url}?dates={date.strftime(format='%Y%m%d')}&limit=200")
    games_json = games_response.json()['events']

    # For each game, build a dict recording current game details.
    if games_json: # If games today.
        for game in games_json:
            competition = game['competitions'][0]
            status = competition['status']

            # Split out the home and away competitors.
            home = next(team for team in competition['competitors'] if team['homeAway'] == 'home')
            away = next(team for team in competition['competitors'] if team['homeAway'] == 'away')

            # Ensure logos for both teams exist locally, downloading from ESPN if needed.
            ensure_team_logo(league_abrv, home['team']['abbreviation'], home['team']['id'], home['team'].get('logo'))
            ensure_team_logo(league_abrv, away['team']['abbreviation'], away['team']['id'], away['team'].get('logo'))

            # Append the dict to the games list.
            games.append({
                'game_id': game['id'],
                'home_abrv': home['team']['abbreviation'],
                'away_abrv': away['team']['abbreviation'],
                'home_score': int(home.get('score') or 0),
                'away_score': int(away.get('score') or 0),
                'home_rank': home.get('curatedRank', {}).get('current', 99), # 99 = unranked.
                'away_rank': away.get('curatedRank', {}).get('current', 99),
                'start_datetime_utc': dt.strptime(game['date'], '%Y-%m-%dT%H:%MZ').replace(tzinfo=tz.utc),
                'start_datetime_local': dt.strptime(game['date'], '%Y-%m-%dT%H:%MZ').replace(tzinfo=tz.utc).astimezone(tz=None), # Convert UTC to local time.
                'status': status['type']['name'], # E.g., STATUS_SCHEDULED, STATUS_IN_PROGRESS, STATUS_END_PERIOD, STATUS_FINAL, STATUS_POSTPONED.
                'state': status['type']['state'], # 'pre', 'in', or 'post'.
                'has_started': True if status['type']['state'] != 'pre' else False,
                'period_num': status['period'],
                'period_type': determine_period_type(status),
                'period_time_remaining': normalise_clock(status.get('displayClock', '0:00')),
                'is_intermission': True if status['type']['name'] == 'STATUS_END_PERIOD' else False,
                # Will set the remaining later, default to False and None for now.
                'home_team_scored': False,
                'away_team_scored': False,
                'scoring_team': None
            })

    # Sort games by game_id, ensuring that order remains consistent after games start/end.
    games = sorted(games, key=lambda x: x['game_id'])

    return games


def get_next_game(team, league_abrv):
    """ Loads next game details for the supplied NCAA hockey team.
    If the team is currently playing, will return details of the current game.

    Args:
        team (str): Abbreviation of the team to pull next game details for.
        league_abrv (str): Abbreviation of the league for which to fetch game data (e.g., 'NCAAMH', 'NCAAWH').

    Returns:
        dict: Dict of next game details or None if not found.
    """

    # Note the current datetime.
    cur_datetime = dt.today().astimezone()
    cur_date = cur_datetime.date()

    # Determine the ESPN team ID for the team specified. If the team can't be found, return None.
    team_id = determine_team_id(team, league_abrv)
    if not team_id:
        print(f'Could not determine {league_abrv} team ID for abbreviation: {team}.')
        return None

    # Ensure the logo for the team exists locally, downloading from ESPN if needed.
    ensure_team_logo(league_abrv, team, team_id)

    # Call the ESPN schedule API for the team specified and store the JSON results.
    url = f'https://site.api.espn.com/apis/site/v2/sports/hockey/{league_slugs[league_abrv]}/teams/{team_id}/schedule'
    schedule_response = session.get(url=url)
    schedule_json = schedule_response.json().get('events', [])

    # Filter results to games that have not already concluded. Get the 0th element, the next game.
    upcoming_games = [game for game in schedule_json if game['competitions'][0]['status']['type']['state'] in ('pre', 'in')]
    next_game_details = upcoming_games[0] if len(upcoming_games) > 0 else None

    if next_game_details:
        competition = next_game_details['competitions'][0]

        # Split out the details of the team specified and their opponent.
        team_details = next(comp for comp in competition['competitors'] if comp['team']['id'] == str(team_id))
        opponent_details = next(comp for comp in competition['competitors'] if comp['team']['id'] != str(team_id))

        # Put together a dictionary with needed details.
        next_game = {
            'home_or_away': team_details['homeAway'],
            'opponent_abrv': opponent_details['team'].get('abbreviation', 'TBD'),
            'start_datetime_utc': dt.strptime(next_game_details['date'], '%Y-%m-%dT%H:%MZ').replace(tzinfo=tz.utc),
            'start_datetime_local': dt.strptime(next_game_details['date'], '%Y-%m-%dT%H:%MZ').replace(tzinfo=tz.utc).astimezone(tz=None),
            'is_today': True if dt.strptime(next_game_details['date'], '%Y-%m-%dT%H:%MZ').replace(tzinfo=tz.utc).astimezone(tz=None).date() == cur_date or dt.strptime(next_game_details['date'], '%Y-%m-%dT%H:%MZ').replace(tzinfo=tz.utc).astimezone(tz=None) < cur_datetime else False, # TODO: clean this up. Needed in case game is still going when date rolls over.
            'has_started': True if competition['status']['type']['state'] == 'in' else False
        }

        return(next_game)

    # If no next game found, return None.
    return None


def get_standings(league_abrv):
    """ Loads current NCAA hockey standings by conference.
    Note that the ESPN API only populates standings during the season, so conferences may be empty in the offseason.

    Args:
        league_abrv (str): Abbreviation of the league for which to fetch standings data (e.g., 'NCAAMH', 'NCAAWH').

    Returns:
        dict: Dict containing all standings by each category.
    """

    # Call the ESPN standings API and store the JSON results.
    url = f'https://site.api.espn.com/apis/v2/sports/hockey/{league_slugs[league_abrv]}/standings'
    standings_response = session.get(url=url)
    standings_json = standings_response.json().get('children', [])

    # Set up structure of the returned dict.
    standings = {
        'retrieved_on': dt.now().astimezone(),
        'conference': {} # Will be populated w/ the API results.
    }

    # Populate the conference dicts w/ details of each team.
    for conference in standings_json:
        entries = conference['standings'].get('entries', [])

        # Skip conferences without meaningful standings data (e.g., Independents, or any conference in the offseason).
        if len(entries) < 2:
            continue

        # Build a list of team details for the conference.
        team_standings = []
        for entry in entries:
            stats = {stat['name']: stat for stat in entry['stats']}
            team_standings.append({
                'team_abrv': entry['team'].get('abbreviation', ''),
                'points': int(stats['points']['value']) if 'points' in stats else 0,
                'rank': int(stats['playoffSeed']['value']) if 'playoffSeed' in stats else 0,
                'has_clinched': False # Not provided by the API.
            })

        # The API doesn't reliably provide a rank, so sort by points and rank by position when needed.
        team_standings = sorted(team_standings, key=lambda x: x['points'], reverse=True)
        if any(team['rank'] == 0 for team in team_standings):
            for rank, team in enumerate(team_standings, start=1):
                team['rank'] = rank
        else:
            team_standings = sorted(team_standings, key=lambda x: x['rank'])

        # Add the conference to the standings dict. Use a shortened abbreviation for the sidebar where the API's is too long.
        conference_abrv = conference_abbreviations.get(conference['name'], conference['abbreviation'])[:4]
        standings['conference'][conference['name']] = {
            'subdivision_abrv': conference_abrv,
            'rank_method': 'Points',
            'team_standings': team_standings
        }

    return standings


def determine_period_type(status):
    """ Determines the period type based on the game status returned by the ESPN API.

    Args:
        status (dict): Status dict of a game as returned by the ESPN API.

    Returns:
        str: 'SO' if in/ended in a shootout, 'OT' if in/ended in overtime, otherwise 'REG'.
    """

    if 'SO' in status['type'].get('shortDetail', '') or 'Shootout' in status['type'].get('detail', ''):
        return 'SO'
    elif status['period'] > 3:
        return 'OT'
    else:
        return 'REG'


def normalise_clock(display_clock):
    """ Normalises the clock string returned by the ESPN API to a consistent MM:SS format.

    Args:
        display_clock (str): Clock string as returned by the ESPN API. E.g., '12:34', '2:19', '0:00'.

    Returns:
        str: Clock string in MM:SS format.
    """

    # Strip any fractions of a second, then zero pad the minutes if needed.
    display_clock = display_clock.split('.')[0]
    clock_parts = display_clock.split(':')
    if len(clock_parts) == 2:
        return f'{clock_parts[0].zfill(2)}:{clock_parts[1].zfill(2)}'
    else:
        return '00:00'


def determine_team_id(team, league_abrv):
    """ Gets the ESPN team ID based on team abbreviation.
    Results are cached per league to avoid repeated API calls.

    Args:
        team (str): Abbreviation of the team.
        league_abrv (str): Abbreviation of the league. E.g., 'NCAAMH', 'NCAAWH'.

    Returns:
        str: ESPN team ID, or None if not found.
    """

    # If the mapping for this league hasn't been built yet, call the ESPN teams API and build it.
    if league_abrv not in team_ids:
        url = f'https://site.api.espn.com/apis/site/v2/sports/hockey/{league_slugs[league_abrv]}/teams?limit=500'
        teams_response = session.get(url=url)
        teams_json = teams_response.json()['sports'][0]['leagues'][0]['teams']

        # Not all teams have an abbreviation, skip those that don't.
        team_ids[league_abrv] = {
            team_details['team']['abbreviation']: team_details['team']['id']
            for team_details in teams_json if team_details['team'].get('abbreviation')
        }

    return team_ids[league_abrv].get(team)


def ensure_team_logo(league_abrv, team_abrv, team_id, logo_url=None):
    """ Ensures a logo for the specified team exists locally, downloading from ESPN if needed.
    Needed since NCAA hockey has 100+ teams, so logos are downloaded and cached on demand rather than bundled.

    Args:
        league_abrv (str): Abbreviation of the league. E.g., 'NCAAMH', 'NCAAWH'.
        team_abrv (str): Abbreviation of the team.
        team_id (str): ESPN team ID, used to build the logo URL if one isn't provided.
        logo_url (str, optional): URL of the team logo per the ESPN API. Defaults to None.
    """

    # If the logo already exists locally, nothing to do.
    logo_path = f'assets/images/{league_abrv}/teams/{team_abrv}.png'
    if os.path.exists(logo_path):
        return

    # Ensure the teams directory exists.
    os.makedirs(os.path.dirname(logo_path), exist_ok=True)

    # Download the logo from ESPN and save locally.
    url = logo_url if logo_url else f'https://a.espncdn.com/i/teamlogos/ncaa/500/{team_id}.png'
    logo_response = session.get(url=url)
    if logo_response.ok:
        with open(logo_path, 'wb') as logo_file:
            logo_file.write(logo_response.content)

    # If the logo couldn't be downloaded, build a simple placeholder with the team abbreviation so image builds don't fail.
    else:
        placeholder = Image.new('RGBA', (len(team_abrv) * 8 + 2, 16), (0, 0, 0, 0))
        placeholder_draw = ImageDraw.Draw(placeholder)
        placeholder_font = ImageFont.load('assets/fonts/Tamzen8x15b.pil')
        placeholder_draw.text((1, 0), team_abrv, font=placeholder_font, fill=(255, 255, 255))
        placeholder.save(logo_path)
