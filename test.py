import asyncio
from fastmcp import Client

async def main():
    async with Client("http://127.0.0.1:8001/mcp") as client:
        result = await client.call_tool(
            name="SendEmailJSON",
            arguments={
                "payload": {
                    "student_email": "tayybar130@gmail.com",
                    "student_name": "John Doe",
                    "task_description": "Complete the research assignment on AI ethics",
                    "supervisor_name": "Dr. Smith",
                    "supervisor_email": "dr.smith@example.com",
                    "document": "https://example.com/assignment-doc",
                    "deadline": "2025-12-25"
                }
            }
        )

        print(result.data)

asyncio.run(main())
