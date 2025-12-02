# fz-telemac

Telemac plugin for the [fz](https://github.com/Funz/fz) parametric computation framework.

This repository contains the model definition and calculator scripts for running Telemac simulations with fz.

## TL;DR

1. Clone this repository:
```bash
git clone https://github.com/Funz/fz-telemac.git
cd fz-telemac
```

Ensure you have docker installed, or if a local Telemac installation is available (then fix the path in `Telemac.sh`).

Install dependencies for Telemac.sh (convert .res binary file in .csv format, from .poi files):
```bash
# required for output extraction in Telemac.sh
pip install https://github.com/CNR-Engineering/PyTelTools/zipball/master
```

2. Install fz (if not already installed):
```bash
pip install git+https://github.com/Funz/fz.git
```

3. Run test case:
```python
import fz
results = fz.fzr(
    input_path="examples/Telemac/t2d_breach.cas/",
    input_variables={}, # no variables to vary in this test case
    model="Telemac", # refers to .fz/models/Telemac.json
    calculators="localhost_Telemac", # refers to .fz/calculators/localhost_Telemac.json
    results_dir="results" # directory to store results
)

print(results)
```

4. Plot results:
```python
import matplotlib.pyplot as plt

plt.plot(results['S'][0]['t2d_breach']['time'].values(),results['S'][0]['t2d_breach']['xylowercenter'].values())
plt.xlabel('Time (s)')
plt.ylabel('Water level (m)')
plt.title('Water level over time')
plt.grid()
plt.show()
```


## Configuration

### Model Configuration

The Telemac model is defined in `.fz/models/Telemac.json`:

```json
{
    "id": "Telemac",
    "varprefix": "$", 
    "formulaprefix": "@", 
    "delim": "()", 
    "commentline": "/",
    "output": {
        "S": "python -c 'import pandas;import glob;import json;print(json.dumps({f.split(\"_S.csv\")[0]:pandas.read_csv(f).to_dict() for f in glob.glob(\"*_S.csv\")}))'",
        "H": "python -c 'import pandas;import glob;import json;print(json.dumps({f.split(\"_H.csv\")[0]:pandas.read_csv(f).to_dict() for f in glob.glob(\"*_H.csv\")}))'"
    }
}
```

The model supports:
- Variables: `$(variable_name)` 
- Formulas: `@(expression)`
- Comments: Lines starting with `/`
- POI (Point Of Interest) extraction from `.poi` files (key=xcoord,ycoord format file):
```
xy1=100.0,200.0
xy2=150.0,250.0
```
- Output: Get H and S (from CSV files extracted in Telemac result) at each time step, for each point of interest.

### Calculator 

**Telemac.sh**: Basic script (including post-processing to get CSV output files) for local Telemac installation, using docker. Modify the path to Telemac binaries to use yours if needed.

The calculator configuration is defined in `.fz/calculators/localhost_Telemac.json`:

```json
{
    "uri": "sh://",
    "models": {
      "Telemac":"bash .fz/calculators/Telemac.sh"
    }
}
```

You can modify the script path to use different calculator scripts (docker, singularity, etc.)


### Input Files

Telemac requires several input files:
- `.cas` file: Main case configuration file
- `.slf` files: Geometry, initial conditions, etc.
- `.cli` file: Boundary conditions
- `.liq` file: Liquid boundaries
- `.poi` file: Points of interest for output extraction (not mandatory in Telemac, but used here for fz output parsing)
- Other data files as specified in the `.cas` file

All input files referenced in the `.cas` file must be present in the same directory.

### Output Configuration


CSV-based outputs are created in post-processing of Telemac.sh script, and parsed in the model configuration as shown above:

```json
{
    ...
    "output": {
        "S": "python -c 'import pandas;import glob;import json;print(json.dumps({f.split(\"_S.csv\")[0]:pandas.read_csv(f).to_dict() for f in glob.glob(\"*_S.csv\")}))'",
        "H": "python -c 'import pandas;import glob;import json;print(json.dumps({f.split(\"_H.csv\")[0]:pandas.read_csv(f).to_dict() for f in glob.glob(\"*_H.csv\")}))'"
    }
}
```
Add some more outputs as needed.


## Sample study

A sample Telemac case (`t2d_breach.cas`) is included in this repository, demonstrating a 2D breach simulation. This case includes all necessary input files and can be used as a template for your own simulations.

Create a parametric study from this case by varying parameters such as breach width and duration: edit the breach.txt file to include variables like `$(breach_width)` and `$(breach_delay)`:
```bash
sed -i 's/50.0/$(breach_width)/' examples/Telemac/t2d_breach.cas/breach.txt
sed -i 's/300.0/$(breach_delay)/' examples/Telemac/t2d_breach.cas/breach.txt
```

Then run the parametric study:
```python
import fz

# Define input variables
input_variables = {
    "breach_width": [40, 50],
    "breach_delay": [200, 300]
}

# Run parametric study
results_grid = fz.fzr(
    input_path="examples/Telemac/t2d_breach.cas/",
    input_variables=input_variables,
    model="Telemac",
    calculators=["localhost_Telemac"]*2, # Use 2 parallel local calculators
    results_dir="results_grid"
)

print(results_grid)
```

And plot results as shown in the TL;DR section.
```python
import matplotlib.pyplot as plt

plt.figure()
for i in range(len(results_grid['S'])):
    plt.plot(results_grid['S'][i]['t2d_breach']['time'].values(),
    results_grid['S'][i]['t2d_breach']['xylowercenter'].values(),
    label=f"Breach width: {results_grid['breach_width'][i]}, Delay: {results_grid['breach_delay'][i]}")
plt.xlabel('Time (s)')
plt.ylabel('Water level (m)')
plt.title('Water level over time for different breach widths')
plt.legend()
plt.grid()
plt.show()
```

## Requirements

- Python 3.9+
- fz python package
- Telemac installation or docker

## License

This project follows the BSD 3-Clause License.

## References

- [Telemac website](http://www.opentelemac.org/)
- [fz framework](https://github.com/Funz/fz)
