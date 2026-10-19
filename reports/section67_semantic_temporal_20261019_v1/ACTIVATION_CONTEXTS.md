# Natural activation context workbook

Each context is from a saved natural code sequence, not a steering generation. TopK100 was applied jointly.

## deepseek_base

### BigCodeBench/336 · token '\n' · activation 32.814 · position 86.1%

```python
py
import pytest
import os
import tempfile
import shutil
from task_func import task_func


@pytest.fixture
def temp_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_di
```

### BigCodeBench/752 · token 'import' · activation 26.893 · position 92.7%

```python
 model.fit(X_train, y_train)

    return model.score(X_test, y_test)

#tests/test_task.py
import pytest
import pandas as pd
import numpy as np
from task import task_func

```

### BigCodeBench/497 · token ' py' · activation 26.775 · position 91.8%

```python
lendar.day_name[local_date.weekday()]

    return weekday

#tests/test_task_func.py
import pytest
from task_func import task_func
from datetime import datetime, timedelta

```

### BigCodeBench/712 · token 'test' · activation 26.308 · position 91.7%

```python

    return result

#tests/test_task_func.py
import os
import shutil
import glob
import pytest
from task_func import task_func

```

### BigCodeBench/3 · token 'test' · activation 26.232 · position 90.2%

```python
n_dict[letter] = np.mean(values)

    return mean_dict

#tests/test_task_func.py
import pytest
import numpy as np
from task_func import task_func

```

### BigCodeBench/5 · token 'test' · activation 26.225 · position 94.2%

```python
** 2 for x in value) / len(value))

    return sd_dict

#tests/test_task_func.py
import pytest
from task_func import task_func

```

### BigCodeBench/279 · token 'test' · activation 26.082 · position 88.5%

```python
rn the hands and the counter
    return hands, counter

#tests/test_task_func.py
import pytest
from task_func import task_func
from collections import Counter

```

### BigCodeBench/873 · token 'test' · activation 25.926 · position 95.8%

```python
return os.path.abspath(file_path)

#tests/test_task_func.py
import os
import csv
import pytest
from task_func import task_func

```

### BigCodeBench/30 · token '\n' · activation 25.876 · position 95.7%

```python
ttribute]}")

    return data[attribute]

#tests/test_task_func.py
import os
import pytest
from task_func import task_func

```

### BigCodeBench/701 · token 'test' · activation 25.826 · position 79.8%

```python
t(X, y)
    score = model.score(X, y)
    return score

#tests/test_task_func.py
import pytest
import pandas as pd
from task_func import task_func

```

### BigCodeBench/453 · token '\n' · activation 25.449 · position 75.3%

```python
     if re.match(pattern, s):
            return s

#tests/test_task_func.py
import pytest
import re
import string
from random import choice
from task_func import task_func

```

### BigCodeBench/778 · token 'test' · activation 25.413 · position 95.1%

```python
ategory].extend(articles)

    return grouped_articles

#tests/test_task_func.py
import pytest
from task_func import task_func

```

### BigCodeBench/415 · token ' py' · activation 25.349 · position 92.1%

```python
icode-escape"))

    return dataframe

#tests/test_task_func.py
import pandas as pd
import pytest
from task_func import task_func

```

### BigCodeBench/949 · token 'test' · activation 25.324 · position 80.0%

```python
(rows, columns)
    df = pd.DataFrame(matrix)
    return df

#tests/test_task.py
import pytest
import pandas as pd
from task import task_func

```

### BigCodeBench/706 · token 'import' · activation 25.313 · position 51.0%

```python
uracy = accuracy_score(y_test, y_pred)
    
    return accuracy

#tests/test_task_func.py
import unittest
import numpy as np
from task_func import task_func

class TestTaskFunc(unittest.TestCase):
    def t
```

## deepseek_finetuned

### BigCodeBench/752 · token '#' · activation 4.916 · position 73.6%

```python
nearRegression()
    model.fit(X_train, y_train)

    return model.score(X_test, y_test)

# Example usage
rng = np.random.default_rng(seed=42)
data = pd.DataFrame({
    'x1': rng.random(100),
    'x2':
```

### BigCodeBench/258 · token ' py' · activation 4.189 · position 42.3%

```python
mat()
    return json.dumps(person)


# Example usage
from datetime import datetime
import pytz

utc_time = datetime(2023, 6, 15, 12, 0, 0, tzinfo=pytz.UTC)
person_json_str = task_func(utc_time)
json_dat
```

### BigCodeBench/630 · token '\n' · activation 3.591 · position 100.0%

```python
k_func(df, 'data.json')

# Check if the JSON file is created and contains the correct data

```

### BigCodeBench/30 · token '#' · activation 3.420 · position 98.3%

```python
l']):
        raise ValueError("Invalid email format.")

    return json_data[attribute]

# Example usage

```

### BigCodeBench/626 · token 'time' · activation 3.262 · position 23.2%

```python
he datetime object from the given timezone to UTC
    date_obj = date_obj.astimezone(pytz.timezone(from_tz))

    # Choose a random timezone
    to_tz = choice(TIMEZONES)

    # Convert the datetime objec
```

### BigCodeBench/1109 · token " '" · activation 3.179 · position 36.9%

```python
download the necessary resources using: nltk.download()

# Note: The file 'sample.txt' and 'data.txt' are provided as examples. You can replace them with your own text files.
# Make sure to keep the fil
```

### BigCodeBench/398 · token '\n' · activation 3.038 · position 57.7%

```python
  return False

# Example usage
import tempfile
import json

temp_dir = tempfile.mkdtemp()
file_path = os.path.join(temp_dir, 'data.json')
with open(file_path, 'w') as f:
    json.dump([{'name': 'Alice
```

### BigCodeBench/81 · token '#' · activation 2.869 · position 77.6%

```python
sponse.json()

    api = Api(app)
    api.add_resource(DataAPI, '/data')

    return app

# Example usage
app = task_func('https://api.example.com/data', 'templates')

```

### BigCodeBench/561 · token 'time' · activation 2.805 · position 19.9%

```python
 date_obj = parser.parse(date_str)

    # Get the timezone objects
    from_tz_obj = pytz.timezone(from_tz)
    to_tz_obj = pytz.timezone(to_tz)

    # Convert the datetime object to the target timezone
 
```

### BigCodeBench/21 · token 'memory' · activation 2.593 · position 43.8%

```python
latform.architecture()[0]

    # Calculate memory usage
    memory_usage = psutil.virtual_memory().percent

    # Return system details in a dictionary
    return {'OS': os_name, 'Architecture': arch, 'Memo
```

### BigCodeBench/127 · token '9' · activation 2.552 · position 38.4%

```python
unt

# Example usage
# task_func('/path/to/root', '/path/to/dest', 'd41d8cd98f00b204e9800998ecf8427e')

# Note: The above example assumes the existence of the root directory and at least one file in RO
```

### BigCodeBench/166 · token '5' · activation 2.478 · position 85.9%

```python
 and public holidays
    business_days = [day for day in business_days if day.weekday() < 5 and day not in country_holidays]

    return business_days

# Example usage
business_days = task_func()

```

### BigCodeBench/797 · token '#' · activation 2.452 · position 71.7%

```python
            brackets_count += len(re.findall(pattern, value))

    return brackets_count

# Example usage
df = pd.DataFrame({'A': ['(a)', 'b', 'c'], 'B': ['d', 'e', '(f)']})

```

### BigCodeBench/109 · token '\n' · activation 2.396 · position 81.2%

```python
'Location': ['store1', 'store2', 'store3', 'store1']
})

ax = task_func(df)
ax.get_title()
# 'Item Distribution by Location'

# You can further customize the chart by modifying the parameters of the fu
```

### BigCodeBench/361 · token 'test' · activation 2.385 · position 65.6%

```python
_name=test_sheet_name, index=False)
task_func(sheet_name='TestSheet', excel_file_location=test_excel_file, csv_file_location=test_csv_file)
os.remove(test_excel_file)
os.remove(test_csv_file)

# Note: Ens
```

## codellama_base

### BigCodeBench/206 · token '\n' · activation 22.468 · position 28.4%

```python
th.exists(file_name):
        raise FileNotFoundError(f'File {file_name} does not exist.')

    with open(file_name, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        json_file = file_n
```

### BigCodeBench/756 · token '\n' · activation 20.996 · position 20.5%

```python
_dir).exists():
        raise ValueError(f'Source directory {source_dir} does not exist.')
    if not Path(target_dir).exists():
        raise ValueError(f'Target directory {target_dir} does not exist.
```

### BigCodeBench/423 · token '\n' · activation 19.154 · position 18.9%

```python
path):
        raise FileNotFoundError('Image file does not exist at the specified path.')

    # Check if the threshold is an integer and in the range 0-255
    if not isinstance(threshold, int) or th
```

### BigCodeBench/971 · token '\n' · activation 17.960 · position 12.6%

```python
exists(directory_path):
        raise ValueError('The provided directory does not exist.')

    directory_path = Path(directory_path)
    if not directory_path.is_dir():
        raise ValueError('The p
```

### BigCodeBench/370 · token '\n' · activation 17.948 · position 20.6%

```python
irectory_path):
        raise FileNotFoundError("The specified directory does not exist.")
    files = []
    for file_path in glob.glob(directory_path + "/*.json"):
        with open(file_path, "r") a
```

### BigCodeBench/790 · token '\n' · activation 17.917 · position 26.2%

```python
olumns:
        raise ValueError(f"Columns {col1} and {col2} not found in the DataFrame.")
    scaler = StandardScaler()
    df[col1] = scaler.fit_transform(df[[col1]])
    df[col2] = scaler.fit_transf
```

### BigCodeBench/604 · token '\n' · activation 17.289 · position 100.0%

```python
.error("Compiler not found.")
    except OSError:
        logging.error("File not found.")

```

### BigCodeBench/875 · token '          ' · activation 16.985 · position 65.7%

```python
64':
                df[col] = df[col].fillna(random.randint(num_range[0], num_range[1]))
            elif df[col].dtype == 'float64':
                df[col] = df[col].fillna(random.uniform(num_range[0], num_ra
```

### BigCodeBench/431 · token '\n' · activation 16.746 · position 27.8%

```python

        raise FileNotFoundError(f'The specified image file does not exist: {image_file}')

    image = cv2.imread(image_file, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f'The
```

### BigCodeBench/878 · token '\n' · activation 16.745 · position 22.2%

```python
 not in df.columns:
        raise ValueError('The target column is not in the DataFrame.')

    # Check if the DataFrame is empty
    if df.empty:
        raise ValueError('The DataFrame is empty.')

 
```

### BigCodeBench/989 · token '      ' · activation 16.025 · position 52.9%

```python
 == 'has_uppercase':
            result['has_uppercase'] = any(c.isupper() for c in text)
        elif predicate == 'has_lowercase':
            result['has_lowercase'] = any(c.islower() for c in text)
     
```

### BigCodeBench/983 · token '\n' · activation 15.487 · position 17.6%

```python
    if df.empty:
        raise ValueError('The DataFrame is empty.')

    if not np.issubdtype(df.dtypes.iloc[0], np.number):
        raise TypeError('The DataFrame contains non-n
```

### BigCodeBench/398 · token '\n' · activation 15.371 · position 25.4%

```python
    if not os.path.exists(file_path):
        return False
    with open(file_path, 'r') as f:
        data = json.load(f)
    return isinstance(data, list) and all(isin
```

### BigCodeBench/275 · token '\n' · activation 15.039 · position 53.3%

```python
    if n < 1:
        raise ValueError("n must be greater than or equal to 1.")
    return list(combinations(range(1, n + 1), 2))

```

### BigCodeBench/357 · token '\n' · activation 14.598 · position 45.8%

```python
    if not isinstance(x, np.ndarray):
        raise TypeError("x must be a numpy.ndarray")
    return norm.pdf(x, 0, 1) + 1j * norm.pdf(x, 2, 2)

```

## codellama_merged

### BigCodeBench/604 · token '\n' · activation 20.469 · position 86.2%

```python
ept FileNotFoundError:
        logging.error("Compiler not found or file does not exist.")
    else:
        logging.info("Compilation process successful.")

```

### BigCodeBench/206 · token '\n' · activation 20.275 · position 16.8%

```python
    if not os.path.exists(file_name):
        raise FileNotFoundError(file_name)
    with open(file_name, 'r', newline='') as csvfile:
        fieldnames = ['id', 'name', 'age']
        write
```

### BigCodeBench/756 · token '\n' · activation 20.005 · position 67.1%

```python
   if not source_dir_path.exists():
        raise ValueError('source_dir does not exist.')
    if not target_dir_path.exists():
        raise ValueError('target_dir does not exist.')

```

### BigCodeBench/578 · token '\n' · activation 16.689 · position 43.8%

```python
se.status_code != requests.codes.OK:
        raise requests.exceptions.HTTPError(response)
    result = response.json()
    for key in result:
        if isinstance(result[key], str):
            resul
```

### BigCodeBench/790 · token '\n' · activation 16.665 · position 100.0%

```python
    if col1 not in df.columns:
        raise ValueError("'col1' is not in the DataFrame.")

```

### BigCodeBench/423 · token '\n' · activation 15.952 · position 12.7%

```python
te threshold value.
    if not os.path.exists(image_path):
        raise FileNotFoundError
    if not isinstance(threshold, int):
        raise ValueError
    if not threshold in range(0, 255):
       
```

### BigCodeBench/983 · token '\n' · activation 15.458 · position 100.0%

```python
    if len(df) == 0:
        raise ValueError("The DataFrame is empty.")

```

### BigCodeBench/989 · token '\n' · activation 14.959 · position 35.3%

```python
    if length < 0:
        raise ValueError("Length must be positive.")
    if len(predicates) == 0:
        return (None, None)
    predicates = list(predicates)

```

### BigCodeBench/275 · token '\n' · activation 14.879 · position 48.8%

```python
    if n < 1:
        raise ValueError("n must be greater than 1")
    else:
        return list(combinations(range(1, n), 2))

```

### BigCodeBench/878 · token '\n' · activation 14.392 · position 7.8%

```python
ueError("The input DataFrame is empty or the target column name is not in the DataFrame.")
    if target is None or target not in data:
        raise ValueError("The target column name is not in the Da
```

### BigCodeBench/115 · token '\n' · activation 13.332 · position 38.2%

```python
umbers) == 0:
        raise ValueError('task_func() requires a non-empty list of numbers')
    else:
        numpy_array = np.array(numbers)
        result = {'mode': mode(numpy_array), 'entropy': entr
```

### BigCodeBench/846 · token '\n' · activation 10.797 · position 7.9%

```python
     return pd.DataFrame(columns=['attribute', 'count'], index=pd.Index([], name='index'))

    if len(obj_list) == 1:
        return pd.DataFrame(columns=['attribute', 'count'], index=pd.Index([], nam
```

### BigCodeBench/1092 · token '\n' · activation 9.960 · position 100.0%

```python
ept Exception as e:
                return []
    except Exception as e:
        return []

```

### BigCodeBench/149 · token '\n' · activation 9.941 · position 58.8%

```python
ements},
            {'Count': np.array([len(element) for element in elements])}
        )
    else:
        return pd.DataFrame(
            {'Element': elements},
            {'Count': np.array([len(
```

### BigCodeBench/841 · token '\n' · activation 9.371 · position 41.9%

```python
    if json_string is None:
        return defaultdict(int, {})
    if json_string is None or json_string is False:
        return defaultdict(int, {})

```

