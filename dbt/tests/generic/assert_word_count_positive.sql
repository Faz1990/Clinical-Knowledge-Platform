{% test assert_word_count_positive(model, column_name) %}

{#
  Fails if any row has a null or non-positive word count.
  Every document that passed the structural gate (EMPTY_CONTENT check) and was
  successfully parsed should have at least one word. A zero here means pdfplumber
  extracted no text — a parsing failure that should surface as a test, not
  silently produce a row with no content.
#}

SELECT *
FROM {{ model }}
WHERE {{ column_name }} IS NULL
   OR {{ column_name }} <= 0

{% endtest %}
