# Rules

## Rules that should happen every day

1. The person needs to sleep from 6-8 hours daily. This can be seen from the bed pressure mat. If there user has pressure for these hours in **total**.
2. The person needs to take their medicine once per day. preferably around 8 in the morning. Max Delay should be at most 1 hour.
3. The person needs to have 3 meals per day. This can be calculated from the fridge contact sensor or the stove/toaster working.
4. The person needs to follow a hygiene. They need to wash hands when coming home from outside, and after cooking. Shower once per day. Wash hands after toilet use.
5. The person needs to Go to the toilet at least one per day. This is seen from the toilet water flow sensor
6. The person needs to open the windows for at least an hour per day.
7. The person should go to the balcony for at least 15 minutes/day.

## Events that show decline:

1. Person leaves Fridge door open for more than 5 minutes
2. Person leaves Balcony doors open, but has left the appartment
3. Reduced meal routine
4. Long sedentary period on the sofa or the chair without kitchen or bathroom activity.
5. Very low room-to-room movement ()
6. Water left running without presense in bathroom (water_running_no_bathroom)

## Hazardous events:

1. Stove left on while resident goes to sleep or leaves appartment (stove_on_left_appartment)
2. Toaster left on while resident leaves appartment or go to sleep (toaster_on_left_appartment)
3. Very long sleep duration (very_long_sleep)
4. Exit from apartment from 12am to 5am (exit_appartment_at_night)
5. Door left open from 12am to 5am for more than 30mins (door_open_at_night)
6. No water use for a full day (no_water_all_day)

# Care Plan

1. Wake up at around 7:00am maxDelay 30min
2. Go to the toilet after waking up
3. Medicine should be taken around 8:00am maxDelay 30min
4. Eat Breakfast at 8:40am maxDelay 1 hour
5. Eat Lunch at around 13:00pm maxDelay 1 hour
6. Go to bed for siesta at around 3:00pm
7. wake up from sieasta at around 5:00pm
8. Eat dinner at around 6:00pm
9. Go to the Balcony at around 7:00pm
10. Have a shower at 8:00pm
11. Go to sleep at around 11:00pm maxDelay 30min
