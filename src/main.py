import flet as ft


def main(page: ft.Page):
    page.title = "Чеклист"
    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Container(
                content=ft.Text("Чеклист"),
                alignment=ft.Alignment.CENTER,
            ),
        )
    )


if __name__ == "__main__":
    ft.run(main)
