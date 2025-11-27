#  TEST_20251127
This branch modifies the branch created on 2025-11-26.
input_for_4.txt uses the new web questionnaire format, while input_for_current.txt uses the current questionnaire format used in the clinic.
The file app_test_uploadversion_5.py has been updated to support both questionnaire formats.

# TEST_20251017
"Initial Consultation Summary from Web Questionnaires in Mental Clinics" app

This is an application designed to generate an initial visit summary from web-based questionnaires used in psychiatric and mental health clinics.
It is intended for use in Japan.

app_test_2.py is a script that generates a text summary based on user input entered on the web.

  =>Please use " ***/input " for that purpose.

app_test_uploadversion.py is a script that generates a text summary from an uploaded text file.

  =>Please use " ***/upload " for that purpose.

# Usage

```
python app_test_5.py
```

open http://127.0.0.1:5000/input

