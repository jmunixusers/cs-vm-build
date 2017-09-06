"""Let's make the Finch robot dance!"""

from finch import Finch
from time import sleep

finch = Finch()

##### CHANGE CODE BELOW THIS LINE #####

finch.led(0, 255, 0)
finch.wheels(0.75, 0.75)
sleep(1.5)

finch.led(0, 0, 255)
finch.wheels(-0.75, -0.75)
sleep(1.5)

finch.halt()
