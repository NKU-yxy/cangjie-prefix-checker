func apply_4_981871<T>(value: T, action: (T) -> T): T {
    action(value)
}

main(): Unit {
    let answer_4_981871: Int64 = apply_4_981871<Int64>(
        16,
        { outer: Int64 => apply_4_981871<Int64>(
            outer,
            { level_4_4_981871: Int64 => apply_4_981871<Int64>(
                level_4_4_981871,
                { level_3_4_981871: Int64 => apply_4_981871<Int64>(
                    level_3_4_981871,
                    { level_2_4_981871: Int64 => apply_4_981871<Int64>(
                        level_2_4_981871,
                        { level_1_4_981871: Int64 => "nested-wrong" }
                    ) }
                ) }
            ) }
        ) }
    )
}
