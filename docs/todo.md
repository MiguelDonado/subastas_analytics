Capas for shiny application: Hidrografia, 3D (Google Maps), Catastro transparente, IGN
rotate api key goolzoom, because i paste it unintentionaly in plain text in claude session


2. Create the view that basically joins everything to ref catastral in gold, maybe not for the application for debug is useful
   On that view, maybe i want to also add a column to remark if it belongs to a lot with more ref catastrales.

¿WHY BOE-B-2026-29802 failed?
There exists several ways to identify a property:
1. Ref catastral
2. Latitude/longitude
3. Exact direction
4. Polygon/parcel
5. Parcela catastral (covers all catastral references that exist on some parcel, on some piece of land)
6. k, the auction failed cuz when showing the information to identify a property

I should write in failure_modes we are just covering ref catastral, that is 99% of cases, and think if we should give a more clear log somewhere or not, than just not valid lots, even though I guess it is hard to tell why is the reason of the not valid lot in code, unless a trivial one (not 20 characteres...), but it is simpler if a person manually inspects the failed announcement, to decypher what was the reason for the not valid lots.


check what to do after i inspect a failed annoouncement, and it has no solution. Should i let it on failed_announcmemtsn, but then is gonna clutter, and make more difficult future new failed announcements.