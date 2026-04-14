# src/api/view_models.py
from typing import Optional
from pydantic import BaseModel, EmailStr, computed_field


class SeasonContext(BaseModel):
    id: str
    name: str
    current_date: str
    games_remaining: int
    is_active: bool = True


class WebContext(BaseModel):
    """
    Consolidates league, GM, and session data for Jinja2 templates.
    All 'monster' logic moved into computed_fields or properties.
    """

    active_tab: str
    league: Optional[dict] = None
    gm: Optional[dict] = None
    user: Optional[dict] = None
    season: Optional[dict] = None
    is_draft_complete: bool = False
    season: Optional[SeasonContext] = None

    # --- League State Helpers ---

    @computed_field
    @property
    def league_name(self) -> str:
        return self.league["name"] if self.league else "—"

    @computed_field
    @property
    def league_state(self) -> str:
        return self.league["state"] if self.league else "lobby"

    @computed_field
    @property
    def is_commissioner(self) -> bool:
        if not self.league or not self.gm:
            return False
        return self.league.get("commissioner_gm_id") == self.gm.get("id")

    # --- GM / User Helpers ---

    @computed_field
    @property
    def gm_display_name(self) -> str:
        if self.gm and self.gm.get("display_name"):
            return self.gm["display_name"]
        return self.user["display_name"] if self.user else "Guest"

    # --- Tab Visibility Logic ---

    @computed_field
    @property
    def visible_tabs(self) -> list[str]:
        # You can move your _tab_visible logic directly in here
        state = self.league_state
        tabs = ["roster", "standings"]
        if state == "lobby":
            tabs.append("settings")
        if self.is_draft_complete:
            tabs.append("stats")
        return tabs

    # Add any other complex fields like 'current_date' or 'games_remaining' here


class UserContext(BaseModel):
    id: Optional[str] = None
    username: str = "Guest"
    email: Optional[EmailStr] = None
    is_authenticated: bool = False
    is_admin: bool = False

    # UI helper
    @property
    def initials(self) -> str:
        return self.username[:2].upper()
