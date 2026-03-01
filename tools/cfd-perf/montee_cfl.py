# %% [markdown]
# Définition d'une loi géométrie à partir des bornes de départ et de fin

# %%
ite_begin, ite_end = 5, 2000
cfl_begin, cfl_end = 1.0, 200.0

ITES = list(range(ite_begin, ite_end + 1))

ratio = cfl_end / cfl_begin

CFLS = [
    cfl_begin * ratio**((it - ite_begin)/(ite_end - ite_begin))
    for it in ITES
]

# %% [markdown]
# Plot

# %%
import plotting
import matplotlib.pyplot as plt

plotting.use_style("paper")

fig, ax = plt.subplots()
plotting.plot_line(ax,ITES,CFLS)

ax.set_xlabel("ITE")
ax.set_ylabel("CFL")
ax.set_title("CFL vs ITE avec une loi géométrique")
ax.legend()
plt.show()


