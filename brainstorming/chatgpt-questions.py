# output += "{:>{}}".format(PlayerFormatter.abbreviate(player.bats), 2)

# Can you convert this to an fstring?


output = "{:>{}}".format("65", 4)
output2 = f"{"65":>4}"
output3 = f"{65:>4}"

print(output)
print(output2)
print(output3)
