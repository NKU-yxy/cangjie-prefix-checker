main(): Unit {
    let values_1_602923: ArrayList<Int64> = ArrayList<Int64>(23)
    values_1_602923.add(43)
    values_1_602923.add(ArrayList<Int64>())
    values_1_602923.add(88, 0)

    let clone_1_602923: () -> ArrayList<Int64> = values_1_602923.clone
    let copied_1_602923: ArrayList<Int64> = clone_1_602923()
}
