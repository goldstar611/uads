
import glob
import re

ret = {}

levels = glob.glob("/home/user/Desktop/game2/levels/multi/*.ldf")
for level in levels:
    with open(level, errors="replace") as f:
        d = f.read()

    this_level_robos = []
    found_robo = False
    for line in d.splitlines():
        if "begin_robo" in line:
            found_robo = True
        if found_robo and "owner" in line:
            match = re.search("\s*owner\s+=\s+([0-9])", line)
            if match:
                owner = match.group(1)
                this_level_robos.append(owner)
                found_robo = False

    level_clean = re.search("l([0-9]{2,3}){2}.ldf", level).group(1)
    ret[level_clean] = this_level_robos

print(ret)

