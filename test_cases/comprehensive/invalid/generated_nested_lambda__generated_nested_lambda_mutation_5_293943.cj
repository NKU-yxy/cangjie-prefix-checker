func apply_5_293943<T>(value: T, action: (T) -> T): T {
    action(value)
}

main(): Unit {
    let answer_5_293943: Int64 = apply_5_293943<Int64>(
        1,
        { outer: Int64 => apply_5_293943<Int64>(
            outer,
            { level_3_5_293943: Int64 => apply_5_293943<Int64>(
                level_3_5_293943,
                { level_2_5_293943: Int64 => apply_5_293943<Int64>(
                    level_2_5_293943,
                    { level_1_5_293943: Int64 => "nested-wrong" }
                ) }
            ) }
        ) }
    )
}
