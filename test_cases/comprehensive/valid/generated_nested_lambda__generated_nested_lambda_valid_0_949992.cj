func apply_0_949992<T>(value: T, action: (T) -> T): T {
    action(value)
}

main(): Unit {
    let answer_0_949992: Int64 = apply_0_949992<Int64>(
        5,
        { outer: Int64 => apply_0_949992<Int64>(
            outer,
            { level_4_0_949992: Int64 => apply_0_949992<Int64>(
                level_4_0_949992,
                { level_3_0_949992: Int64 => apply_0_949992<Int64>(
                    level_3_0_949992,
                    { level_2_0_949992: Int64 => apply_0_949992<Int64>(
                        level_2_0_949992,
                        { level_1_0_949992: Int64 => level_1_0_949992 + 3 }
                    ) }
                ) }
            ) }
        ) }
    )
}
