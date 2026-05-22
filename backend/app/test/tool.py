import json

def convert_object_to_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)

if __name__ == "__main__":
  
    data = [
      {
          "type": "function",
          "function": {
              "name": "get_schema",
              "description": "Retrieves the structure information (column names, data types) of a specified table in a database. This tool must be called before writing any SQL if the table structure is not explicitly known.",
              "parameters": {
                  "type": "object",
                  "properties": {
                      "table_name": {
                          "type": "string", 
                          "description": "Table name."
                      }
                  },
                  "required": ["table_name"]
              }
          }
      },
      {
          "type": "function",
          "function": {
              "name": "sample_data",
              "description": "Retrieves sample data from the table. Use this when you need to understand the specific range of values, enumeration value format, or data characteristics of a field.",
              "parameters": {
                  "type": "object",
                  "properties": {
                      "table_name": {
                          "type": "string",
                          "description": "Table name."
                      },
                      "limit": {
                          "type": "integer",
                          "description": "The number of rows returned defaults to 5.",
                          "default": 5
                      }
                  },
                  "required": ["table_name"]
              }
          }
      },
      {
          "type": "function",
          "function": {
              "name": "execute_sql",
              "description": "Execute SQL queries in DuckDB. Only SELECT statements are allowed. Please ensure that you have verified the table and column names using get_schema before calling this tool.",
              "parameters": {
                  "type": "object",
                  "properties": {
                      "sql": {
                          "type": "string",
                          "description": "A complete SQL SELECT statement that conforms to DuckDB syntax."
                      }
                  },
                  "required": ["sql"]
              }
          }
      },
      {
          "type": "function",
          "function": {
              "name": "run_python",
              "description": "{run_python_desc}",
              "parameters": {
                  "type": "object",
                  "properties": {
                      "code": {
                          "type": "string",
                          "description": (
                              "Python source code to execute. "
                              "Use `conn` to query DuckDB. "
                              "Use `print()` for text output. "
                              "The last expression's value is captured automatically."
                          )
                      }
                  },
                  "required": ["code"]
              }
          }
      }
  ]
    json_data = convert_object_to_json(data)
    print(json_data)