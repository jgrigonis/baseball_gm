"""
Award stories in the news feed put each award on its own line
(src/api/services/news/events.py). The roundup, Gold Glove and Silver
Slugger stories already written ran their awards together in one
paragraph: break them where one award ends and the next begins
("...(.299). Pacific League Batting Champion: ...").
"""

VERSION = 54


def upgrade(conn):
    conn.execute(
        r"""UPDATE league_news
            SET body = regexp_replace(body, '\. (?=[^.:]{1,60}: )', E'.\n', 'g')
            WHERE kind = 'season_award'
              AND (key LIKE 'award:roundup:%' OR key LIKE 'award:gloves:%'
                   OR key LIKE 'award:sluggers:%')"""
    )
