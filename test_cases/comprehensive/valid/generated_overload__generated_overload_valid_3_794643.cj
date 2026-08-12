main(): Unit {
    let values_3_794643: ArrayList<Int64> = ArrayList<Int64>(26)
    values_3_794643.add(14)
    values_3_794643.add(ArrayList<Int64>())
    values_3_794643.add(1, 0)

    let clone_3_794643: () -> ArrayList<Int64> = values_3_794643.clone
    let copied_3_794643: ArrayList<Int64> = clone_3_794643()
}
