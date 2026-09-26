# src/ui/navigation.py — portal entry and sign-in return

`apply_catalog_handoff` validates `preset`, `load=reflex|sealed`, optional net
volume `vb` and reflex tuning `fb` before changing the design. Names must exist
in the allowed Studio library; numbers must be finite and within widget bounds.
Missing drivers and invalid links show a warning and leave current parameters
unchanged. Explicit shared/public project links take priority.

A valid link saves existing work before switching (save failures block the
switch), detaches cloud identity and comparison variants, and opens a new Box
Design. Supplied dimensions select Manual mode so alignment cannot overwrite
them. Each query signature applies once per session; edits survive reruns.
Fresh links suppress resuming the last cloud project. Workspace navigation
clears consumed catalog query parameters. No catalog is modified.

`remember_auth_destination` writes a ten-minute SameSite=Lax navigation cookie
on the sign-in page, Secure on HTTPS. `restore_auth_destination` restores only
allowlisted query keys after authenticated OIDC returns to the root in a new
Streamlit session, then clears the cookie. Explicit new links take precedence.
Credentials and arbitrary redirect URLs are never stored or accepted. Values
remain untrusted and pass normal catalog/public-project validation. Payloads
over 3,000 encoded characters are not stored. The cookie requires browser
JavaScript and cookies; it does not change authentication or permissions.

The allowlist includes `lf_aid`, the opaque anonymous visit id from
[usage tracking](usage.md), so a sign-up can be linked to its portal visit
without any long-lived analytics cookie.

The cookie is shared by tabs on the same origin: the latest sign-in destination
wins. Local email sign-in keeps the existing query and needs no restoration.
Tests cover handoff state, invalid inputs, reruns, and auth destination filtering.
