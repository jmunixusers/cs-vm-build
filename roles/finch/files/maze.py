"""Help the Finch navigate a maze."""

from finch import Finch
from time import sleep

# initialize state
finch = Finch()
done = False

while not done:

    # read current sensor values
    x, y, z, tap, shake = finch.acceleration()
    left_light, right_light = finch.light()
    left_obstacle, right_obstacle = finch.obstacle()
    temp = finch.temperature()

    # did it just get dark?
    if left_light < 0.35 or right_light < 0.35:
        done = True

    # RED: is something in the way?
    elif left_obstacle or right_obstacle:
        finch.led(255, 0, 0)
        finch.wheels(-0.75, -0.75)
        sleep(0.50)

    # GREEN: all clear, move ahead!
    else:
        finch.led(0, 255, 0)
        finch.wheels(0.75, 0.75)
        sleep(0.05)

# grand finale
finch.buzzer(1.5, 10000)
finch.halt()
