# Marker-component ablation on 119 DeepSeek contamination cases

Coverage within this preselected cohort is not precision/specificity on arbitrary generated code. Identical existing regular expressions; no new inference. Frozen capture text is distinct from current re-extracted alpha-zero text.

| Configuration | Frozen captured text | Current alpha-zero text |
|---|---:|---:|
| comments_only | 107/119 | 108/119 |
| import_only | 96/119 | 96/119 |
| class_only | 93/119 | 94/119 |
| comments_plus_import | 117/119 | 117/119 |
| comments_plus_class | 113/119 | 114/119 |
| full | 119/119 | 119/119 |

## Frozen tasks missed by comments alone

### BigCodeBench/91

First marker: task_func_import; pass at alpha -5: False

```python
lope, intercept, r_value, p_value, std_err), ax

#task_1.py
import pandas as pd
from task_func import task_func

data = pd.read_csv("data.csv")
result, ax = task_func(data, "Column1", "Column2")

```

Matched lines: {"task_func_import": {"char": 1454, "line": "from task_func import task_func"}}
### BigCodeBench/122

First marker: task_func_import; pass at alpha -5: False

```python
func_test.py
import unittest
from unittest.mock import patch
import numpy as np
from task_func import task_func

class TestTaskFunc(unittest.TestCase):
    @patch('random.randint', return_value=50)
    def test_task_func(self, mock_randint):
        my_list = [2, 3, 5]
        result = task_func(my_list)
        self.assertTrue(10 <= len(result) <= 110)  # Expecting the length to be within the range after adding a random number between  and 100
        self.assertIsInstance(result, np.ndarray)

```

Matched lines: {"task_func_import": {"char": 1154, "line": "from task_func import task_func"}, "test_class": {"char": 1187, "line": "class TestTaskFunc(unittest.TestCase):"}}
### BigCodeBench/166

First marker: task_func_import; pass at alpha -5: True

```python
try_holidays]

    return business_days

#main.py
from datetime import datetime
from task_func import task_func

# Example usage
start_date = datetime(2023, 1, 1)
end_date = datetime(2023, 12, 31)
country = 'US'

business_days = task_func(start_date, end_date, country)

```

Matched lines: {"task_func_import": {"char": 1991, "line": "from task_func import task_func"}}
### BigCodeBench/435

First marker: task_func_import; pass at alpha -5: False

```python
ry
    data_df = pd.DataFrame(data)

    return data_df

#main.py
import random
from task_func import task_func

# Set the seed for the random number generator
random.seed(0)

# Call the task_func function with the input data
df = task_func("John", 30, "A10B", 5000.0, "This is a bio with spaces")

# Print the resulting DataFrame

```

Matched lines: {"task_func_import": {"char": 1968, "line": "from task_func import task_func"}}
### BigCodeBench/459

First marker: task_func_import; pass at alpha -5: True

```python
 unittest
import os
import subprocess
import time
from datetime import datetime
from task_func import task_func


class TestTaskFunc(unittest.TestCase):
    def setUp(self):
        self.script_dir = os.path.join(os.path.dirname(__file__), 'scripts')
        self.scripts = ['script1.sh', 'script2.sh']
        self.delay = 2

    def test_task_func(self):
        timestamps = task_func(self.script_dir, self.scripts, self.delay)
        self.assertEqual(len(timestamps), len(self.scripts))
        for timestamp in timestamps:
            self.assertRegex(timestamp, r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')

        for script in self.scripts:
    
```

Matched lines: {"task_func_import": {"char": 1627, "line": "from task_func import task_func"}, "test_class": {"char": 1661, "line": "class TestTaskFunc(unittest.TestCase):"}}
### BigCodeBench/634

First marker: task_func_import; pass at alpha -5: False

```python
etitions))
    return stats.mode(flat_list)

#task_func_test.py
import unittest
from task_func import task_func


class TestTaskFunc(unittest.TestCase):
    def test_task_func(self):
        # Test case 1: List with multiple repetitions
        input_list = ['A', 'B', 'C']
        repetitions = 10
        expected_result = ('A', 10)
        self.assertEqual(task_func(input_list, repetitions), expected_result)

        # Test case 2: List with no repetitions
        input_list = [1, 2, 3]
        repetitions = 1
        expected_result = (1, 1)

```

Matched lines: {"task_func_import": {"char": 1174, "line": "from task_func import task_func"}, "test_class": {"char": 1208, "line": "class TestTaskFunc(unittest.TestCase):"}}
### BigCodeBench/685

First marker: task_func_import; pass at alpha -5: True

```python
    return Counter(chain.from_iterable(list_of_lists))

#main.py
from task_func import task_func

```

Matched lines: {"task_func_import": {"char": 639, "line": "from task_func import task_func"}}
### BigCodeBench/787

First marker: task_func_import; pass at alpha -5: False

```python
   return max(distances)

#task_func_test.py
import unittest
import numpy as np
from task_func import task_func

class TestTaskFunc(unittest.TestCase):
    def test_same_length(self):
        array1 = np.array([2, 3, 4])
        array2 = np.array([1, 5, 2])
        self.assertAlmostEqual(task_func(array1, array2), 4.123105625617661)

    def test_different_length(self):
        array1 = np.array([2, 3, 4])
        array2 = np.array([1, 5])
        with self.assertRaises(ValueError):
            task_func(array1, array2)

    def test_empty_arrays(self):
        array1 = np.array([])
        array2 = np.array([])
        self.assertEqual(task_
```

Matched lines: {"task_func_import": {"char": 1798, "line": "from task_func import task_func"}, "test_class": {"char": 1831, "line": "class TestTaskFunc(unittest.TestCase):"}}
### BigCodeBench/823

First marker: test_class; pass at alpha -5: True

```python
ion
    return mean, std

#task_func_test.py
import unittest
import task_func


class TestTaskFunc(unittest.TestCase):
    def test_task_func(self):
        # Test with default parameters
        mean, std = task_func.task_func()
        self.assertAlmostEqual(mean, 0.1, places=1)
        self.assertAlmostEqual(std, 0.0, places=1)

        # Test with custom parameters
        mean, std = task_func.task_func(samples=5, delay=0.05)
        self.assertAlmostEqual(mean, 0.05, places=1)
        self.assertAlmostEqual(std, 0.0, places=1)

        # Test with large number of samples
        mean, std = task_func.task_func(samples=100, delay=0.001)

```

Matched lines: {"test_class": {"char": 1634, "line": "class TestTaskFunc(unittest.TestCase):"}}
### BigCodeBench/840

First marker: task_func_import; pass at alpha -5: False

```python
trix
from sklearn.metrics import roc_curve, auc
import matplotlib.pyplot as plt
from task_func import task_func

```

Matched lines: {"task_func_import": {"char": 1861, "line": "from task_func import task_func"}}
### BigCodeBench/858

First marker: test_class; pass at alpha -5: False

```python

import unittest
from task_1 import task_func
from collections import Counter


class TestTask1(unittest.TestCase):
    def test_task_func(self):
        # Test with a fixed seed
        expected_counts = Counter({'v': 48, 'b': 47, 'n': 46, 'r': 46, 'k': 46, 'z': 46, 'c': 44, 'e': 43, 'q': 43, 'l': 43, 'y': 42, 'm': 42, 'a': 42, 'u': 42, 'd': 36, 'o': 34, 'j': 34, 'g': 34, 'f': 33, 'h': 33, 'p': 32, 'w': 30, 'x': 30, 'i': 29, 't': 28, 's': 27})
        self.assertEqual(task_func(1000, seed=123), expected_counts)

        # Test with a different seed
        expected_counts = Counter({'v': 2, 'l': 2, 'p': 1, 'i': 1, 'q': 1, 'e': 1, 'm': 1, 'a'
```

Matched lines: {"test_class": {"char": 1999, "line": "class TestTask1(unittest.TestCase):"}}
### BigCodeBench/1030

First marker: task_func_import; pass at alpha -5: False

```python
etter 1', 'Letter 2', 'Letter 3'])

    return df

#main.py
import pandas as pd
from task_func import task_func

# Generate the DataFrame
df = task_func()

# Save the DataFrame to a CSV file
df.to_csv('output.csv', index=False)

# Print the first 5 rows of the DataFrame

```

Matched lines: {"task_func_import": {"char": 1083, "line": "from task_func import task_func"}}

## Earlier non-comment marker despite a later matching comment

